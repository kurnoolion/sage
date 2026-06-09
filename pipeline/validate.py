"""Validation (D-008 invariants), generalized + subtype-aware.

  KG ⊨ ontology : every entity/relation type is declared; every relation's
                  from/to types satisfy the relationship's domain/range
                  **accounting for the entity-type hierarchy** (a SIPMethod
                  satisfies a Message domain because SIPMethod subtype_of Message).
  KG ⊨ corpus   : every (non-curated/non-external) provenance clause resolves in
                  the corpus, and its anchor text locates within that clause
                  (including the clause's named child units).

Returns (errors, warnings). Errors are hard (type/domain/range violations);
corpus-resolution misses are warnings (anchor drift, R7) destined for review.
"""
import re

from . import ontology

_WS = re.compile(r"\s+")


def _norm_ws(s):
    """Collapse every run of whitespace (spaces, tabs, newlines, NBSP \\xa0, and
    other Unicode spaces — all matched by \\s) to a single space, and trim ends.

    The corpus stores prose with paragraph newlines, indentation prefixes, and
    NBSPs (e.g. 'annex\\xa0A'); an LLM quoting the same span uses ordinary single
    spaces. Comparing both sides whitespace-normalized keeps the anchor check
    verbatim on *content* (KG ⊨ corpus, D-008) while ignoring whitespace shape,
    which removes false-positive 'anchor not found' warnings without weakening
    the real check (hallucinated/paraphrased wording still fails to match).
    """
    return _WS.sub(" ", s).strip()


def _anchor_in(corpus, clause, anchor, hay_cache):
    if not anchor:
        return True
    hay = hay_cache.get(clause)
    if hay is None:
        hay = _norm_ws(corpus.haystack(clause))
        hay_cache[clause] = hay
    a = _norm_ws(anchor).strip(" .;:,")
    if a and a in hay:
        return True
    # tolerate a leading word or two of drift
    w = a.split(" ")
    return any(" ".join(w[i:]) in hay for i in range(1, max(1, len(w) - 2)))


def validate(entities, relations, corpus, version=None):
    errs, warns = [], []
    version = version or corpus.version
    etypes = ontology.ENTITY_TYPES
    rtypes = ontology.RELATIONSHIP_TYPES
    hay_cache = {}                         # clause -> whitespace-normalized haystack
    by_id = {e["id"]: e for e in entities}
    allids = set(by_id) | {r["id"] for r in relations}

    # --- KG ⊨ ontology : entity types ---
    for e in entities:
        if e["type"] not in etypes:
            errs.append("entity %s undeclared type %s" % (e["id"], e["type"]))

    # --- KG ⊨ corpus : entity provenance ---
    for e in entities:
        for p in e.get("defined_in", []):
            if p.get("curated") or p.get("external") or p.get("version") != version:
                continue
            cl = p.get("clause")
            if cl not in corpus:
                warns.append("entity %s defined_in clause %s not in corpus" % (e["id"], cl)); continue
            if not _anchor_in(corpus, cl, p.get("anchor"), hay_cache):
                warns.append("entity %s anchor not found in %s: %r" % (e["id"], cl, (p.get("anchor") or "")[:40]))

    # --- KG ⊨ ontology : relation types + subtype-aware domain/range ---
    for r in relations:
        if r["type"] not in rtypes:
            errs.append("relation %s undeclared type %s" % (r["id"], r["type"])); continue
        spec = rtypes[r["type"]]
        if r["from"] not in by_id:
            errs.append("relation %s from unknown entity %s" % (r["id"], r["from"]))
        if r["to"] not in by_id:
            errs.append("relation %s to unknown entity %s" % (r["id"], r["to"]))
        ft = by_id.get(r["from"], {}).get("type")
        tt = by_id.get(r["to"], {}).get("type")
        if ft and not ontology.domain_range_ok(spec["domain"], ft):
            errs.append("relation %s (%s): from-type %s not in domain %s" % (r["id"], r["type"], ft, spec["domain"]))
        if tt and not ontology.domain_range_ok(spec["range"], tt):
            errs.append("relation %s (%s): to-type %s not in range %s" % (r["id"], r["type"], tt, spec["range"]))
        # --- KG ⊨ corpus : relation provenance ---
        for p in r.get("provenance", []):
            if p.get("curated") or p.get("external") or p.get("clause") is None or p.get("version") != version:
                continue
            cl = p["clause"]
            if cl not in corpus:
                warns.append("relation %s provenance clause %s not in corpus" % (r["id"], cl)); continue
            if not _anchor_in(corpus, cl, p.get("anchor"), hay_cache):
                warns.append("relation %s anchor not found in %s: %r" % (r["id"], cl, (p.get("anchor") or "")[:40]))

    # --- lifecycle field sanity (D-011) ---
    from .config import RELEASES
    relset = set(RELEASES)
    for obj, what in ([(e, "entity") for e in entities] + [(r, "relation") for r in relations]):
        for rid in obj.get("observed_in") or []:
            if rid not in relset:
                errs.append("%s %s observed_in %s not a known release" % (what, obj["id"], rid))
        for f in ("introduced_in", "valid_until"):
            v = obj.get(f)
            if v is not None and v not in relset:
                errs.append("%s %s %s=%s not a known release" % (what, obj["id"], f, v))
        if obj.get("supersedes") is not None and obj["supersedes"] not in allids:
            errs.append("%s %s supersedes unknown id %s" % (what, obj["id"], obj["supersedes"]))

    return errs, warns
