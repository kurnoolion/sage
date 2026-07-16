"""Evaluate a pipeline snapshot against a hand-built gold KG (workstream C2).

The hand-built RRC pilot (rrc-pilot/knowledge-graph/kg.json, clauses 5.3.3 +
5.3.5 of TS 38.331) is expert ground truth — the thing KARMA's evaluation
lacked. This scores a pipeline snapshot against it:

    python3 -m pipeline.eval_gold --spec "TS 38.331" --version 19.2.0 --label pilot-scope

Scope conventions:
  * gold entities  = domain entities only (concept-scheme scaffolding —
    DomainRoot/Stratum/ProtocolLayer/Release — excluded);
  * gold relations = behavioural types only (IN_LAYER/BROADER/NEXT_RELEASE
    excluded).

Matching is by (entity type, whitespace/hyphen/case-normalized label) — ids
differ by construction (gold uses curated names, the pipeline derives labels
from clause titles / vocab / LLM output). If the snapshot has
alias-suggestions.json, accepted-shape merge proposals are applied first, so
a surface form that aliases to a canonical label still matches.

Reported per type and overall:
  * entity precision  (pipeline entities that exist in gold)
  * entity recall     (gold entities the pipeline found)
  * relation precision/recall (type + matched endpoints)
  * C3, when LLM facts are present: the fraction of pipeline-accepted LLM
    relations that gold does NOT support — our local analogue of KARMA's
    LLM-judged (0.831) vs human-expert (0.625) gap.

Read the numbers with the granularity asymmetry (D-005) in mind: the
deterministic pass anchors *every* titled subclause as a Procedure, while the
gold KG curates ~10 — Procedure "precision" against gold is expected to be
low and is not by itself a defect. The per-type table exists precisely so
that story stays visible.
"""
import argparse
import json
import logging
import os
import re

from . import snapshot

logger = logging.getLogger(__name__)

SCAFFOLD_ENTITY_TYPES = {"DomainRoot", "Stratum", "ProtocolLayer", "Release"}
SCAFFOLD_RELATION_TYPES = {"IN_LAYER", "BROADER", "NEXT_RELEASE"}

_NORM = re.compile(r"[\s\-_]+")


def _norm(label):
    return _NORM.sub(" ", label or "").strip().lower()


def _ekey(e):
    return (e["type"], _norm(e["label"]))


def load_gold(path):
    with open(path) as f:
        kg = json.load(f)
    ents = [e for e in kg["entities"] if e["type"] not in SCAFFOLD_ENTITY_TYPES]
    rels = [r for r in kg["relations"] if r["type"] not in SCAFFOLD_RELATION_TYPES]
    return kg, ents, rels


def _alias_map(snap_dir):
    """surface_id -> canonical_id for merge-shaped alias suggestions, if any."""
    path = os.path.join(snap_dir, "alias-suggestions.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    return {s["surface_id"]: s["canonical_id"] for s in data.get("suggestions", [])
            if s.get("proposal") == "merge"}


def _match_entities(gold_ents, pipe_ents, aliases):
    """Return (gold_id -> pipe_id map, per-type tallies)."""
    by_id = {e["id"]: e for e in pipe_ents}
    # A pipeline entity is addressable by its own key and, when it is alias-merged,
    # by its canonical counterpart's key too.
    pipe_keys = {}
    for e in pipe_ents:
        pipe_keys.setdefault(_ekey(e), e["id"])
    for surface, canonical in aliases.items():
        if surface in by_id and canonical in by_id:
            pipe_keys.setdefault(_ekey(by_id[surface]), canonical)

    g2p = {}
    for g in gold_ents:
        pid = pipe_keys.get(_ekey(g))
        if pid is not None:
            g2p[g["id"]] = pid
    return g2p


def _tally(pairs):
    """pairs of (type, matched_bool) -> {type: (matched, total)} + overall."""
    per = {}
    for typ, ok in pairs:
        m, t = per.get(typ, (0, 0))
        per[typ] = (m + (1 if ok else 0), t + 1)
    total_m = sum(m for m, _ in per.values())
    total_t = sum(t for _, t in per.values())
    return per, (total_m, total_t)


def _fmt_ratio(m, t):
    return "%3d/%-3d %s" % (m, t, ("%.2f" % (m / t)) if t else "  — ")


def evaluate(spec, version, label=None, gold_path="rrc-pilot/knowledge-graph/kg.json"):
    snap_dir = snapshot.dir_for(spec, version, label)
    with open(os.path.join(snap_dir, "snapshot.json")) as f:
        snap = json.load(f)
    if not os.path.isabs(gold_path):
        gold_path = os.path.join(snapshot._ROOT, gold_path)
    _, gold_ents, gold_rels = load_gold(gold_path)
    aliases = _alias_map(snap_dir)

    pipe_ents = snap["entities"]
    pipe_rels = snap["relations"]
    pipe_by_id = {e["id"]: e for e in pipe_ents}

    # --- entities ---------------------------------------------------------
    g2p = _match_entities(gold_ents, pipe_ents, aliases)
    recall_pairs = [(g["type"], g["id"] in g2p) for g in gold_ents]
    gold_keys = {_ekey(g) for g in gold_ents}
    # alias-merged surfaces count as their canonical for precision too
    def pipe_hit(e):
        if _ekey(e) in gold_keys:
            return True
        canon = aliases.get(e["id"])
        return canon in pipe_by_id and _ekey(pipe_by_id[canon]) in gold_keys
    precision_pairs = [(e["type"], pipe_hit(e)) for e in pipe_ents]
    ent_recall, ent_recall_total = _tally(recall_pairs)
    ent_prec, ent_prec_total = _tally(precision_pairs)

    # --- relations (type + matched endpoints) ------------------------------
    p2g_ent = {}
    for gid, pid in g2p.items():
        p2g_ent.setdefault(pid, gid)
    gold_rel_keys = {(r["type"], r["from"], r["to"]) for r in gold_rels}

    def rel_recall_ok(r):
        pf, pt = g2p.get(r["from"]), g2p.get(r["to"])
        if pf is None or pt is None:
            return False
        return any(pr["type"] == r["type"]
                   and _resolve(pr["from"]) == pf and _resolve(pr["to"]) == pt
                   for pr in pipe_rels)

    def _resolve(pid):
        """alias-merged surface ids resolve to their canonical id."""
        return aliases.get(pid, pid)

    def rel_prec_ok(r):
        gf, gt = p2g_ent.get(_resolve(r["from"])), p2g_ent.get(_resolve(r["to"]))
        if gf is None or gt is None:
            return False
        return (r["type"], gf, gt) in gold_rel_keys

    rel_recall, rel_recall_total = _tally([(r["type"], rel_recall_ok(r)) for r in gold_rels])
    rel_prec, rel_prec_total = _tally([(r["type"], rel_prec_ok(r)) for r in pipe_rels])

    # --- C3: LLM facts unsupported by gold ---------------------------------
    llm_rels = [r for r in pipe_rels if r.get("extractor") == "llm"]
    llm_supported = sum(1 for r in llm_rels if rel_prec_ok(r))
    c3 = {"llm_relations": len(llm_rels), "supported_by_gold": llm_supported,
          "unsupported_fraction": round(1 - llm_supported / len(llm_rels), 3)
          if llm_rels else None}

    # --- report -------------------------------------------------------------
    print("SAGE gold eval — %s %s%s vs %s" % (
        spec, version, " [label=%s]" % label if label else "", os.path.relpath(gold_path, snapshot._ROOT)))
    print("  aliases applied: %d merge proposals\n" % len(aliases))
    print("  ENTITIES        %-22s %-22s" % ("recall (gold found)", "precision (pipe in gold)"))
    for typ in sorted(set(ent_recall) | set(ent_prec)):
        rm, rt = ent_recall.get(typ, (0, 0))
        pm, pt = ent_prec.get(typ, (0, 0))
        print("    %-14s %-22s %-22s" % (typ, _fmt_ratio(rm, rt), _fmt_ratio(pm, pt)))
    print("    %-14s %-22s %-22s" % ("TOTAL", _fmt_ratio(*ent_recall_total), _fmt_ratio(*ent_prec_total)))
    print("\n  RELATIONS       %-22s %-22s" % ("recall (gold found)", "precision (pipe in gold)"))
    for typ in sorted(set(rel_recall) | set(rel_prec)):
        rm, rt = rel_recall.get(typ, (0, 0))
        pm, pt = rel_prec.get(typ, (0, 0))
        print("    %-14s %-22s %-22s" % (typ, _fmt_ratio(rm, rt), _fmt_ratio(pm, pt)))
    print("    %-14s %-22s %-22s" % ("TOTAL", _fmt_ratio(*rel_recall_total), _fmt_ratio(*rel_prec_total)))
    if c3["llm_relations"]:
        print("\n  C3 (LLM facts vs expert gold): %d LLM relations, %d supported by gold, "
              "unsupported fraction = %.3f"
              % (c3["llm_relations"], c3["supported_by_gold"], c3["unsupported_fraction"]))
    else:
        print("\n  C3: no LLM relations in this snapshot (deterministic-only run)")

    out = {
        "spec": spec, "version": version, "label": label,
        "gold": os.path.relpath(gold_path, snapshot._ROOT),
        "aliases_applied": len(aliases),
        "entities": {"recall": {t: list(v) for t, v in ent_recall.items()},
                     "recall_total": list(ent_recall_total),
                     "precision": {t: list(v) for t, v in ent_prec.items()},
                     "precision_total": list(ent_prec_total)},
        "relations": {"recall": {t: list(v) for t, v in rel_recall.items()},
                      "recall_total": list(rel_recall_total),
                      "precision": {t: list(v) for t, v in rel_prec.items()},
                      "precision_total": list(rel_prec_total)},
        "c3_llm_vs_gold": c3,
        "unmatched_gold_entities": sorted(g["id"] for g in gold_ents if g["id"] not in g2p),
    }
    path = os.path.join(snap_dir, "eval-gold.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("  full result -> %s" % path)
    return out


def main():
    ap = argparse.ArgumentParser(description="Score a snapshot against a hand-built gold KG.")
    ap.add_argument("--spec", default="TS 38.331")
    ap.add_argument("--version", default="19.2.0")
    ap.add_argument("--label", default=None)
    ap.add_argument("--gold", default="rrc-pilot/knowledge-graph/kg.json")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    evaluate(a.spec, a.version, a.label, a.gold)


if __name__ == "__main__":
    main()
