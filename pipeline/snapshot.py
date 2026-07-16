"""Write a per-(spec,release) extraction snapshot + review queue (D-010 stage 4/5).

A *snapshot* is the validated extraction for one spec version, in the same shape
as the pilot's kg.json (so the existing viewers/derive() consume it unchanged).
Snapshots are the **source of truth** that the cross-release derive() (D-012)
later folds into the unified KG.

Anything low-confidence, malformed, or flagged by validation goes to the
**review queue** rather than being silently trusted (D-010 + risk register).
"""
import json
import os
import time

from . import align, ontology

# Repo root, so a relative out_root resolves to the repo's snapshots dir no matter
# what CWD the pipeline is launched from (matches corpus.py).
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def merge(*record_lists):
    """Union entities/relations by id; first occurrence wins, provenance merged."""
    out = {}
    for lst in record_lists:
        for rec in lst:
            prev = out.get(rec["id"])
            if prev is None:
                out[rec["id"]] = rec
            else:
                key = "defined_in" if "defined_in" in rec else "provenance"
                seen = {(p.get("clause"), p.get("anchor")) for p in prev.get(key, [])}
                for p in rec.get(key, []):
                    if (p.get("clause"), p.get("anchor")) not in seen:
                        prev.setdefault(key, []).append(p)
    return list(out.values())


def conflict_groups(relations):
    """Same (from, relation-type), different objects, on a **functional** type.

    KARMA CRA-derived, deterministic (doc 05 §2.7/§3.1): only the grouping is
    adopted — no LLM debate, and no auto-drop, because under multi-release
    modeling (D-011/D-012) a conflicting object is often the change signal
    derive() exists to capture, not noise. Functional types are flagged in the
    ontology (``functional: True``); everything else is legitimately
    multi-valued and never grouped.
    """
    groups = {}
    for r in relations:
        if ontology.RELATIONSHIP_TYPES.get(r["type"], {}).get("functional"):
            groups.setdefault((r["from"], r["type"]), []).append(r)
    out = []
    for (frm, typ), rs in sorted(groups.items()):
        if len({r["to"] for r in rs}) < 2:
            continue
        out.append({"kind": "conflict-group", "from": frm, "type": typ,
                    "members": [{"id": r["id"], "to": r["to"],
                                 "confidence": r.get("confidence"),
                                 "extractor": r.get("extractor"),
                                 "anchor": (r.get("provenance") or [{}])[0].get("anchor"),
                                 "clause": (r.get("provenance") or [{}])[0].get("clause")}
                                for r in rs]})
    return out


def build_review_queue(entities, relations, warns):
    items = conflict_groups(relations)
    for e in entities:                            # ambiguous / low-confidence entity typing
        if e.get("confidence") in ("low", "med"):
            items.append({"kind": "ambiguous-entity-type", "id": e["id"],
                          "type": e["type"], "label": e["label"],
                          "confidence": e["confidence"], "reason": e.get("review"),
                          "clause": (e.get("defined_in") or [{}])[0].get("clause")})
    for r in relations:
        if r.get("confidence") in ("low", "med"):
            items.append({"kind": "low-confidence-relation", "id": r["id"],
                          "type": r["type"], "from": r["from"], "to": r["to"],
                          "confidence": r["confidence"],
                          "anchor": (r.get("provenance") or [{}])[0].get("anchor")})
    for w in warns:
        items.append({"kind": "validation-warning", "detail": w})
    return items


def dir_for(spec, version, label=None, out_root="pipeline/snapshots"):
    """Resolve a snapshot directory. A ``label`` (e.g. a model name) puts the run
    in its own sub-dir so parallel runs over the same spec/version don't collide.
    Single source of truth shared by write(), viz, and compare."""
    if not os.path.isabs(out_root):
        out_root = os.path.join(_ROOT, out_root)
    d = os.path.join(out_root, "%s-%s" % (spec.replace(" ", "").replace(".", ""), version))
    return os.path.join(d, label) if label else d


def write(cfg, entities, relations, errs, warns, ue_report, out_root="pipeline/snapshots", label=None):
    out_dir = dir_for(cfg.spec, cfg.version, label, out_root)
    os.makedirs(out_dir, exist_ok=True)

    snap = {
        "spec": cfg.spec, "version": cfg.version, "release": cfg.release,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entity_count": len(entities), "relation_count": len(relations),
        "entities": entities, "relations": relations,
        "validation": {"errors": errs, "warnings": warns},
    }
    suggestions, backend = align.suggest(entities)
    aliases = {"spec": cfg.spec, "version": cfg.version, "backend": backend,
               "rho": align.rho(), "suggestions": suggestions}
    review = build_review_queue(entities, relations, warns) + align.review_items(suggestions)

    paths = {}
    for name, obj in (("snapshot.json", snap),
                      ("review-queue.json", review),
                      ("alias-suggestions.json", aliases),
                      ("ue-filter-report.json", ue_report)):
        p = os.path.join(out_dir, name)
        with open(p, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        paths[name] = p
    return out_dir, paths
