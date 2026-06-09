"""Deterministic extractors (D-010 pipeline stage 2).

Conservative, high-precision pass that runs *before* the LLM. Its job is to lay
down the **canonical entity backbone + structural edges** that the LLM extraction
and entity-resolution then attach behavioural facts to — not to mine behaviour
itself (that is the LLM's job). So it only emits things that are unambiguous from
structure or controlled vocabulary:

  * Procedures   — from UE clause titles (clause graph).
  * SIPMethod    — controlled vocabulary tokens appearing in UE prose.
  * SIPHeader    — controlled vocabulary tokens appearing in UE prose.
  * INVOKES      — explicit cross-references ("... as specified in subclause 5.1.x").

Everything is anchored (provenance resolves in the corpus) so it passes KG⊨corpus.
Behavioural edges (EXCHANGES / STARTS / HAS_PRECONDITION / …) are deliberately
left to the LLM extractor.
"""
import re
from . import records

# --- controlled vocabularies ------------------------------------------------
SIP_METHODS = ["REGISTER", "INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "SUBSCRIBE",
               "NOTIFY", "PUBLISH", "MESSAGE", "REFER", "INFO", "PRACK", "UPDATE"]

SIP_HEADERS = [
    "P-Access-Network-Info", "P-Preferred-Identity", "P-Asserted-Identity",
    "P-Associated-URI", "P-Called-Party-ID", "P-Visited-Network-ID",
    "P-Preferred-Service", "P-Asserted-Service", "P-Profile-Key",
    "Service-Route", "Path", "Contact", "Authorization", "WWW-Authenticate",
    "Security-Client", "Security-Verify", "Security-Server", "Require",
    "Proxy-Require", "Supported", "Route", "Privacy", "Feature-Caps",
    "Accept-Contact", "Reject-Contact", "Request-Disposition", "Expires",
]

_GENERIC_TITLES = {"general", "void", "introduction", "scope", "", "purpose"}

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
        e = records.entity(cfg, "Procedure", title, key, anchor=title,
                           extractor="deterministic:procedure")
        add_entity(e)
        proc_at_clause[cl.get("number") or key] = e["id"]

    # 2. SIP vocabulary (methods + headers) ---------------------------------
    method_re = {m: re.compile(r"\b%s\b" % re.escape(m)) for m in SIP_METHODS}
    header_re = {h: re.compile(r"\b%s\b" % re.escape(h)) for h in SIP_HEADERS}
    for key in ue_keys:
        text = corpus[key].get("text") or ""
        for m, rx in method_re.items():
            if rx.search(text):
                add_entity(records.entity(cfg, "SIPMethod", m, key, anchor=m,
                                          extractor="deterministic:sip-method"))
        for h, rx in header_re.items():
            if rx.search(text):
                add_entity(records.entity(cfg, "SIPHeader", h, key, anchor=h,
                                          extractor="deterministic:sip-header"))

    # 3. INVOKES from explicit cross-references -----------------------------
    xref_re = re.compile(r"(?:as )?(?:specified|described|defined) in subclause\s+(\d+(?:\.\d+)+[A-Z]?)")
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
