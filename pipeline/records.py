"""Builders for KG entity/relation records in the canonical SAGE shape.

Matches the shape emitted by rrc-pilot/build_layers.py so snapshots are
interchangeable with the pilot KG and feed the same validators / views:

    entity   = {id, type, label, defined_in:[prov], observed_in, introduced_in,
                valid_until, supersedes, +extractor metadata}
    relation = {id, type, from, to, modality, confidence, procedure_ctx, attrs,
                provenance:[prov], observed_in, introduced_in, valid_until, supersedes}

``prov`` (per-version provenance, D-011) = {release, spec, version, clause, anchor}.
"""
from . import ids


def life(release, agnostic=False):
    return {"observed_in": ([] if agnostic or not release else [release]),
            "introduced_in": None, "valid_until": None, "supersedes": None}


def prov(cfg, clause, anchor=None):
    return {"release": cfg.release, "spec": cfg.spec, "version": cfg.version,
            "clause": clause, "anchor": anchor}


def entity(cfg, typ, label, clause, anchor=None, **extra):
    e = {"id": ids.canonical_id(typ, label, spec=cfg.spec),
         "type": typ, "label": label,
         "defined_in": [prov(cfg, clause, anchor)]}
    e.update(life(cfg.release))
    e.update(extra)                       # e.g. extractor="deterministic:procedure"
    return e


def relation(cfg, rtype, frm, to, clause, anchor=None, *, modality="deterministic",
             confidence="high", procedure_ctx=None, attrs=None, rid=None, **extra):
    r = {"id": rid or _rel_id(rtype, frm, to),
         "type": rtype, "from": frm, "to": to,
         "modality": modality, "confidence": confidence,
         "procedure_ctx": procedure_ctx, "attrs": attrs or {},
         "provenance": [prov(cfg, clause, anchor)]}
    r.update(life(cfg.release))
    r.update(extra)
    return r


def _rel_id(rtype, frm, to):
    # stable, content-derived id (order-independent re-ingestion, D-012)
    f = frm.split("/")[-1]
    t = to.split("/")[-1]
    return "rel:%s:%s:%s" % (rtype.lower(), f, t)
