"""Deterministic extractors (D-010 pipeline stage 2).

Conservative, high-precision pass that runs *before* the LLM. Its job is to lay
down the **canonical entity backbone + structural edges** that the LLM extraction
and entity-resolution then attach behavioural facts to — not to mine behaviour
itself (that is the LLM's job). So it only emits things that are unambiguous from
structure or controlled vocabulary:

  * Procedures   — from UE clause titles (clause graph).
  * Vocab        — per-spec controlled-vocabulary tokens appearing in UE prose
                   (``cfg.vocab``: SIP methods/headers for 24.229; RRC messages,
                   timers, states, UE variables, bearers for 38.331).
  * INVOKES      — explicit cross-references ("... as specified in subclause 5.1.x").

Everything is anchored (provenance resolves in the corpus) so it passes KG⊨corpus.
Behavioural edges (EXCHANGES / STARTS / HAS_PRECONDITION / …) are deliberately
left to the LLM extractor.
"""
import re
from . import records

_GENERIC_TITLES = {"general", "void", "introduction", "scope", "", "purpose"}

# Titles that are structurally NOT procedures — data / qualifier / section-header
# clauses (e.g. "Parameters contained in the ISIM", "IMS AKA as a security
# mechanism", "IMS AKA - general"). We keep them as anchors but demote to
# confidence=med → review queue, because precise typing is the LLM's job
# (D-010/D-015), not a title regex. Note "abnormal procedures" IS a procedure, so
# we match "abnormal cases" but deliberately not "abnormal procedures".
_AMBIGUOUS_TITLE = re.compile(
    r"(?i)(\bparameters?\b|as a security mechanism|[-–]\s*general$"
    r"|\babnormal cases\b|\bstored information\b|\bintroduction\b)")

# procedure clause levels under the UE subtree we treat as procedure anchors
_PROC_LEVELS = (3, 4, 5)


def extract(corpus, cfg, ue_keys):
    """Run all deterministic extractors over the UE clause set.

    Returns (entities, relations). Entities are de-duplicated by id (first
    provenance wins; observed-in is unioned for vocab seen in many clauses).
    """
    ent_by_id = {}
    relations = []

    def add_entity(e):
        prev = ent_by_id.get(e["id"])
        if prev is None:
            ent_by_id[e["id"]] = e
        else:                                   # merge provenance (vocab in many clauses)
            seen = {(p["clause"], p["anchor"]) for p in prev["defined_in"]}
            for p in e["defined_in"]:
                if (p["clause"], p["anchor"]) not in seen:
                    prev["defined_in"].append(p)
        return ent_by_id[e["id"]]

    ue_set = set(ue_keys)
    proc_at_clause = {}                          # clause-number -> procedure entity id

    # 1. Procedures from UE clause titles -----------------------------------
    for key in ue_keys:
        cl = corpus[key]
        if "/" in key:                           # named sub-unit, not a procedure clause
            continue
        title = (cl.get("title") or "").strip()
        if title.lower() in _GENERIC_TITLES:
            continue
        if cl.get("level") not in _PROC_LEVELS:
            continue
        if not (cl.get("text") or "").strip():
            continue
        ambiguous = bool(_AMBIGUOUS_TITLE.search(title))
        extra = {"confidence": "med", "review": "ambiguous-procedure-title"} if ambiguous \
            else {"confidence": "high"}
        e = records.entity(cfg, "Procedure", title, key, anchor=title,
                           extractor="deterministic:procedure", **extra)
        add_entity(e)
        proc_at_clause[cl.get("number") or key] = e["id"]

    # 2. controlled vocabulary (per-spec, cfg.vocab) -------------------------
    vocab_re = [(typ, term, re.compile(r"\b%s\b" % re.escape(term)))
                for typ, terms in cfg.vocab for term in terms]
    for key in ue_keys:
        text = corpus[key].get("text") or ""
        for typ, term, rx in vocab_re:
            if rx.search(text):
                add_entity(records.entity(cfg, typ, term, key, anchor=term,
                                          extractor="deterministic:vocab:%s" % typ))

    # 3. INVOKES from explicit cross-references -----------------------------
    # Both idioms: "as specified in subclause 5.1.1.2" (24.229) and the bare
    # "as specified in 5.3.3.4" (38.331). Target must resolve to a known UE
    # procedure clause, so the looser pattern stays high-precision.
    xref_re = re.compile(r"(?:as )?(?:specified|described|defined) in "
                         r"(?:(?:sub)?clause\s+)?(\d+(?:\.\d+)+[A-Z]?)")
    for key in ue_keys:
        if "/" in key:
            continue
        src_pid = proc_at_clause.get(corpus[key].get("number") or key)
        if not src_pid:
            continue
        text = corpus[key].get("text") or ""
        for m in xref_re.finditer(text):
            target = m.group(1)
            tgt_pid = proc_at_clause.get(target)
            if tgt_pid and tgt_pid != src_pid:
                relations.append(records.relation(
                    cfg, "INVOKES", src_pid, tgt_pid, key,
                    anchor=m.group(0), confidence="high", procedure_ctx="xref"))

    # de-dup relations by id (keep first)
    seen, uniq = set(), []
    for r in relations:
        if r["id"] in seen:
            continue
        seen.add(r["id"]); uniq.append(r)

    return list(ent_by_id.values()), uniq
