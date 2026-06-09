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


def build_review_queue(entities, relations, warns):
    items = []
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


def write(cfg, entities, relations, errs, warns, ue_report, out_root="pipeline/snapshots"):
    if not os.path.isabs(out_root):
        out_root = os.path.join(_ROOT, out_root)
    out_dir = os.path.join(out_root, "%s-%s" % (cfg.spec.replace(" ", "").replace(".", ""), cfg.version))
    os.makedirs(out_dir, exist_ok=True)

    snap = {
        "spec": cfg.spec, "version": cfg.version, "release": cfg.release,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entity_count": len(entities), "relation_count": len(relations),
        "entities": entities, "relations": relations,
        "validation": {"errors": errs, "warnings": warns},
    }
    review = build_review_queue(entities, relations, warns)

    paths = {}
    for name, obj in (("snapshot.json", snap),
                      ("review-queue.json", review),
                      ("ue-filter-report.json", ue_report)):
        p = os.path.join(out_dir, name)
        with open(p, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        paths[name] = p
    return out_dir, paths
