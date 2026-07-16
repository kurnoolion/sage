"""Share-safe run report — compact, paste-friendly summary of labeled runs.

    python3 -m pipeline.report --spec "TS 38.331" --version 19.2.0 llm-v1 llm-v2

Gathers, for each label: entity/relation counts (deterministic vs LLM, by
type), validation + review-queue tallies, alias-suggestion summary (backend,
ρ, distance histogram, top pairs), eval-gold results incl. C3 when present —
and for each label pair the id-overlap Jaccards + object-divergence count.

**Share-safety contract**: the output contains ONLY entity/relation ids,
entity labels (extracted spec terms, truncated to 60 chars), counts and
metrics. It never prints anchors, clause text, review-queue details, or any
verbatim corpus prose — so the block is safe to paste off-machine, unlike the
snapshot files themselves (which are gitignored for 3GPP copyright).
Everything is deterministically ordered, so two reports diff cleanly.
"""
import argparse
import itertools
import json
import os
from collections import Counter

from . import snapshot
from .compare import _object_divergence, _setcmp

_HIST_BUCKETS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.01]


def _load(snap_dir, name):
    path = os.path.join(snap_dir, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _trunc(s, n=60):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def _section(title):
    print("\n== %s ==" % title)


def _label_report(spec, version, label):
    snap_dir = snapshot.dir_for(spec, version, label)
    snap = _load(snap_dir, "snapshot.json")
    if snap is None:
        print("\n== [%s] == NO SNAPSHOT at %s" % (label, snap_dir))
        return None
    ents, rels = snap["entities"], snap["relations"]
    _section("[%s] %s %s" % (label, spec, version))
    print("generated: %s" % snap.get("generated"))

    det_e = sum(1 for e in ents if str(e.get("extractor", "")).startswith("deterministic"))
    llm_e = sum(1 for e in ents if e.get("extractor") == "llm")
    det_r = sum(1 for r in rels if str(r.get("extractor", "")).startswith("deterministic")
                or r.get("procedure_ctx") == "xref")
    llm_r = sum(1 for r in rels if r.get("extractor") == "llm")
    print("entities: %d (det %d / llm %d)   relations: %d (det %d / llm %d)"
          % (len(ents), det_e, llm_e, len(rels), det_r, llm_r))
    print("entity types: %s" % dict(Counter(e["type"] for e in ents).most_common()))
    print("relation types: %s" % dict(Counter(r["type"] for r in rels).most_common()))
    print("llm confidence: %s" % dict(Counter(
        r.get("confidence", "?") for r in rels if r.get("extractor") == "llm").most_common()))

    v = snap.get("validation", {})
    print("validation: %d errors, %d warnings" % (len(v.get("errors", [])), len(v.get("warnings", []))))

    review = _load(snap_dir, "review-queue.json") or []
    print("review queue: %d %s" % (len(review), dict(Counter(i.get("kind", "?") for i in review).most_common())))
    conflicts = [i for i in review if i.get("kind") == "conflict-group"]
    for c in conflicts[:5]:
        print("  conflict: %s %s -> %d objects" % (c.get("type"), c.get("from"), len(c.get("members", []))))

    aliases = _load(snap_dir, "alias-suggestions.json")
    if aliases and aliases.get("suggestions"):
        sugg = aliases["suggestions"]
        hist = Counter()
        for s in sugg:
            for b in _HIST_BUCKETS:
                if s["distance"] < b:
                    hist["<%.1f" % b] += 1
                    break
        merges = sum(1 for s in sugg if s["proposal"] == "merge")
        print("aliases: %d scored (%s, rho=%s) -> %d merge / %d new-entity"
              % (len(sugg), aliases.get("backend"), aliases.get("rho"),
                 merges, len(sugg) - merges))
        print("  distance histogram: %s" % {k: hist[k] for k in sorted(hist)})
        for s in sugg[:8]:
            print("  %.3f %-10s %s (%s) -> %s" % (
                s["distance"], s["proposal"], _trunc(s["surface_label"], 40),
                s["surface_type"], _trunc(s["canonical_label"], 40)))
    elif aliases is not None:
        print("aliases: 0 scored (backend=%s)" % aliases.get("backend"))

    ev = _load(snap_dir, "eval-gold.json")
    if ev:
        er, ep = ev["entities"]["recall_total"], ev["entities"]["precision_total"]
        rr, rp = ev["relations"]["recall_total"], ev["relations"]["precision_total"]
        print("eval-gold: entity recall %d/%d, precision %d/%d | relation recall %d/%d, precision %d/%d"
              % (er[0], er[1], ep[0], ep[1], rr[0], rr[1], rp[0], rp[1]))
        print("  entity recall by type: %s" % {t: "%d/%d" % tuple(v) for t, v in
                                               sorted(ev["entities"]["recall"].items())})
        print("  relation recall by type: %s" % {t: "%d/%d" % tuple(v) for t, v in
                                                 sorted(ev["relations"]["recall"].items()) if v[1]})
        c3 = ev.get("c3_llm_vs_gold", {})
        if c3.get("llm_relations"):
            print("  C3: %d LLM relations, %d supported by gold, unsupported fraction = %s"
                  % (c3["llm_relations"], c3["supported_by_gold"], c3["unsupported_fraction"]))
    else:
        print("eval-gold: not run (python3 -m pipeline.eval_gold --label %s)" % label)
    return snap


def _pair_report(a, b, snap_a, snap_b, samples=6):
    rels_a = {r["id"]: r for r in snap_a["relations"]}
    rels_b = {r["id"]: r for r in snap_b["relations"]}
    ents_a = {e["id"]: e for e in snap_a["entities"]}
    ents_b = {e["id"]: e for e in snap_b["entities"]}
    llm_a = {k: v for k, v in rels_a.items() if v.get("extractor") == "llm"}
    llm_b = {k: v for k, v in rels_b.items() if v.get("extractor") == "llm"}

    _section("%s vs %s" % (a, b))
    for name, ca, cb in (("entities", ents_a, ents_b),
                         ("relations", rels_a, rels_b),
                         ("LLM relations", llm_a, llm_b)):
        cmp_ = _setcmp(ca, cb)
        print("%-14s both=%-4d only-%s=%-4d only-%s=%-4d jaccard=%.3f"
              % (name, cmp_["both"], a, len(cmp_["only_a"]), b, len(cmp_["only_b"]),
                 cmp_["jaccard"]))
    div = _object_divergence(llm_a, llm_b)
    print("object divergence: %d subjects" % len(div))
    for d in div[:samples]:
        print("  %s %s: only-%s=%d only-%s=%d both=%d"
              % (_trunc(d["from"], 50), d["type"], a, len(d["only_a"]),
                 b, len(d["only_b"]), len(d["both"])))


def main():
    ap = argparse.ArgumentParser(description="Compact, share-safe report over labeled runs.")
    ap.add_argument("--spec", default="TS 38.331")
    ap.add_argument("--version", default="19.2.0")
    ap.add_argument("labels", nargs="+", help="run labels to report (1 or more)")
    a = ap.parse_args()

    print("SAGE run report — %s %s — labels: %s" % (a.spec, a.version, ", ".join(a.labels)))
    print("(share-safe: ids/labels/counts only — no anchors, no clause text)")
    snaps = {}
    for lab in a.labels:
        snaps[lab] = _label_report(a.spec, a.version, lab)
    for x, y in itertools.combinations([l for l in a.labels if snaps.get(l)], 2):
        _pair_report(x, y, snaps[x], snaps[y])


if __name__ == "__main__":
    main()
