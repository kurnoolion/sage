"""Compare extraction snapshots — e.g. two LLMs over the same corpus.

    python3 -m pipeline.compare --spec "TS 24.229" --version 19.6.0 qwen llama

Loads ``snapshots/<SPEC>-<VER>/<label>/snapshot.json`` for each label and reports
where the runs agree and differ — per-label counts, then for each pair the
entity / relation / LLM-only-fact set overlap (by id, so same id == same fact).
Writes ``compare.json`` under ``snapshots/<SPEC>-<VER>/`` for the full lists.

Because the deterministic spine is identical across runs, the interesting signal
is the **LLM** facts (`extractor == "llm"`): the LLM-relation overlap is how much
the two models agree on what they extracted.
"""
import argparse
import itertools
import json
import os
import sys

from . import snapshot


def _load(spec, version, label):
    path = os.path.join(snapshot.dir_for(spec, version, label), "snapshot.json")
    if not os.path.exists(path):
        sys.exit("no snapshot for label %r at %s\n  run it first: "
                 "python3 -m pipeline.run --spec %r --version %s --label %s"
                 % (label, path, spec, version, label))
    with open(path) as f:
        return json.load(f)


def _counts(snap):
    rels = snap["relations"]
    ents = snap["entities"]
    return {
        "entities": len(ents),
        "relations": len(rels),
        "llm_relations": sum(1 for r in rels if r.get("extractor") == "llm"),
        "llm_entities": sum(1 for e in ents if e.get("extractor") == "llm"),
        "errors": len(snap.get("validation", {}).get("errors", [])),
        "warnings": len(snap.get("validation", {}).get("warnings", [])),
    }


def _setcmp(ids_a, ids_b):
    a, b = set(ids_a), set(ids_b)
    union = a | b
    return {"a": len(a), "b": len(b), "both": len(a & b),
            "only_a": sorted(a - b), "only_b": sorted(b - a),
            "jaccard": round(len(a & b) / len(union), 3) if union else 1.0}


def _rel_brief(r):
    return "%s: %s -> %s (%s)" % (r["type"], r["from"], r["to"], r.get("confidence", "?"))


def _object_divergence(rels_a, rels_b):
    """Cross-label object disagreement (doc 05 §3.1): group each side's relations
    by (from, type) and report keys BOTH labels assert but with different object
    sets — "model A says X, model B says Y about the same subject". Reported for
    all relation types (it is a diff view, not a conflict verdict — most SAGE
    relations are legitimately multi-valued; the functional-type conflict check
    lives in snapshot.conflict_groups)."""
    def groups(rels):
        g = {}
        for r in rels.values():
            g.setdefault((r["from"], r["type"]), set()).add(r["to"])
        return g
    ga, gb = groups(rels_a), groups(rels_b)
    out = []
    for key in sorted(set(ga) & set(gb)):
        if ga[key] != gb[key]:
            out.append({"from": key[0], "type": key[1],
                        "both": sorted(ga[key] & gb[key]),
                        "only_a": sorted(ga[key] - gb[key]),
                        "only_b": sorted(gb[key] - ga[key])})
    return out


def compare(spec, version, labels, samples=8, out=None):
    snaps = {lab: _load(spec, version, lab) for lab in labels}
    rels = {lab: {r["id"]: r for r in s["relations"]} for lab, s in snaps.items()}
    ents = {lab: {e["id"]: e for e in s["entities"]} for lab, s in snaps.items()}
    llm_rels = {lab: {rid: r for rid, r in rels[lab].items() if r.get("extractor") == "llm"}
                for lab in labels}

    print("SAGE snapshot comparison — %s %s" % (spec, version))
    print("  labels: %s\n" % ", ".join(labels))

    # per-label counts table
    cols = ["entities", "relations", "llm_relations", "llm_entities", "errors", "warnings"]
    print("  %-16s %s" % ("metric", "".join("%14s" % lab[:13] for lab in labels)))
    counts = {lab: _counts(snaps[lab]) for lab in labels}
    for c in cols:
        print("  %-16s %s" % (c, "".join("%14d" % counts[lab][c] for lab in labels)))
    print()

    pairs = []
    for a, b in itertools.combinations(labels, 2):
        rel_cmp = _setcmp(rels[a], rels[b])
        llm_cmp = _setcmp(llm_rels[a], llm_rels[b])
        ent_cmp = _setcmp(ents[a], ents[b])
        divergence = _object_divergence(llm_rels[a], llm_rels[b])
        pairs.append({"a": a, "b": b, "relations": rel_cmp,
                      "llm_relations": llm_cmp, "entities": ent_cmp,
                      "llm_object_divergence": divergence})

        print("  === %s vs %s ===" % (a, b))
        print("  entities     : both=%d  only-%s=%d  only-%s=%d  jaccard=%.3f"
              % (ent_cmp["both"], a, len(ent_cmp["only_a"]), b, len(ent_cmp["only_b"]), ent_cmp["jaccard"]))
        print("  relations    : both=%d  only-%s=%d  only-%s=%d  jaccard=%.3f"
              % (rel_cmp["both"], a, len(rel_cmp["only_a"]), b, len(rel_cmp["only_b"]), rel_cmp["jaccard"]))
        print("  LLM relations: both=%d  only-%s=%d  only-%s=%d  jaccard=%.3f  (model agreement)"
              % (llm_cmp["both"], a, len(llm_cmp["only_a"]), b, len(llm_cmp["only_b"]), llm_cmp["jaccard"]))
        for lab, key, others in ((a, "only_a", b), (b, "only_b", a)):
            ex = llm_cmp[key][:samples]
            if ex:
                print("    LLM facts only %s found (not %s), first %d:" % (lab, others, len(ex)))
                for rid in ex:
                    print("      %s" % _rel_brief(rels[lab][rid]))
        print("  object divergence: %d (from, type) subjects where both models assert "
              "but objects differ" % len(divergence))
        for d in divergence[:samples]:
            print("    %s %s: only-%s=%s  only-%s=%s" % (
                d["from"], d["type"], a, d["only_a"] or "-", b, d["only_b"] or "-"))
        print()

    if out is None:
        out = os.path.join(snapshot.dir_for(spec, version), "compare.json")
    with open(out, "w") as f:
        json.dump({"spec": spec, "version": version, "labels": labels,
                   "counts": counts, "pairs": pairs}, f, indent=2, ensure_ascii=False)
    print("  full diff -> %s" % out)
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Compare two or more extraction snapshots by label.")
    ap.add_argument("--spec", default="TS 24.229")
    ap.add_argument("--version", default="19.6.0")
    ap.add_argument("labels", nargs="+", help="run labels to compare (2 or more)")
    ap.add_argument("--samples", type=int, default=8, help="example divergent facts to print per side")
    ap.add_argument("--out", default=None, help="path for compare.json (default: under the snapshot dir)")
    a = ap.parse_args()
    if len(a.labels) < 2:
        ap.error("give at least two labels to compare")
    compare(a.spec, a.version, a.labels, samples=a.samples, out=a.out)


if __name__ == "__main__":
    main()
