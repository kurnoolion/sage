"""UE-relevance filter (D-010 pipeline stage 1).

SAGE only models the **UE-side** of each spec. For TS 24.229 the UE behaviour is
structurally isolated in clause 5.1 ("Procedures at the UE"); 5.2–5.13 are the
network elements (P-CSCF, S-CSCF, …). So the filter is primarily *structural*
(clause-prefix), with an actor-term fallback for clauses outside the structural
core, and explicit drops for Void/empty/annex material.

Returns the selected clause keys plus a ``report`` explaining what was kept and
dropped — the report is reviewable (R5 coverage risk) and never silently lossy.
"""
from . import config


def _has_text(clause):
    return bool((clause.get("text") or "").strip())


def select(corpus, cfg=None):
    cfg = cfg or config.get(corpus.spec, corpus.version)
    kept, dropped = [], []

    for key, cl in corpus.items():
        title = (cl.get("title") or "").strip()
        # hard drops -------------------------------------------------------
        if any(key.startswith(p) for p in cfg.drop_clause_prefixes):
            dropped.append((key, "drop-prefix")); continue
        if title.lower() == "void":
            dropped.append((key, "void")); continue
        if not _has_text(cl):
            dropped.append((key, "no-text")); continue

        # structural include: UE clause subtree -----------------------------
        structural = any(key == p or key.startswith(p + ".") or key.startswith(p)
                         for p in cfg.ue_clause_prefixes)
        if structural:
            kept.append(key); continue

        # actor-term fallback for clauses outside the structural core --------
        text = (title + "\n" + cl.get("text", "")).lower()
        ue_hit = any(t in text for t in cfg.ue_actor_terms)
        net_hit = any(t in text for t in cfg.network_actor_terms)
        if ue_hit and not net_hit:
            kept.append(key)
        else:
            dropped.append((key, "not-ue"))

    report = {
        "spec": corpus.spec, "version": corpus.version,
        "total_clauses": len(corpus.clauses),
        "kept": len(kept),
        "dropped": len(dropped),
        "kept_by_structure": sum(
            1 for k in kept if any(k == p or k.startswith(p) for p in cfg.ue_clause_prefixes)),
        "drop_reasons": _tally(r for _, r in dropped),
    }
    return kept, report


def _tally(reasons):
    out = {}
    for r in reasons:
        out[r] = out.get(r, 0) + 1
    return out
