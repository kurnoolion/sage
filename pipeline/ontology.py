"""Shared, spec-agnostic ontology (TBox) for SAGE.

This is the single source of truth for entity/relationship *types* across all
specs. The RRC pilot (`rrc-pilot/rrc_model.py`) predates this module and still
carries its own copy; it should eventually import from here. For now this is a
**superset** (RRC types + IMS additions) so the extraction pipeline has one
schema to validate against (D-010: "one shared ontology").

Design notes
------------
* The entity-type hierarchy lives here via ``subtype_of`` (root ``Entity``),
  exactly as in the pilot. IMS introduces a few subtypes so SIP constructs slot
  under the existing abstractions:
      SIPMethod, SIPResponse   subtype_of  Message
      SIPHeader, Identity      subtype_of  InformationElement
      NetworkElement           subtype_of  Entity
  Because they are subtypes, the existing ``EXCHANGES`` / ``CONTAINS`` edges
  already cover "UE sends a REGISTER" and "REGISTER carries a P-Access-Network-Info
  header" — *provided the validator is subtype-aware* (it is; see ``validate.py``
  and ``domain_range_ok`` below). That is the whole point of subtyping here.
"""

# ---------------------------------------------------------------------------
# Entity types  (name -> {desc, subtype_of, attrs})
# ---------------------------------------------------------------------------
ENTITY_TYPES = {
    # --- structural / shared (carried from the RRC pilot) ---
    "Entity":             {"desc": "Root of the entity-type hierarchy.", "subtype_of": None, "attrs": []},
    "DomainRoot":         {"desc": "Top of the domain concept scheme (the UE).", "subtype_of": "Entity", "attrs": []},
    "Stratum":            {"desc": "A protocol stratum (Access / Non-Access).", "subtype_of": "Entity", "attrs": []},
    "ProtocolLayer":      {"desc": "A protocol-stack layer (RRC, MAC, …, IMS).", "subtype_of": "Entity", "attrs": []},
    "Procedure":          {"desc": "A UE behavioural procedure defined in a clause.", "subtype_of": "Entity", "attrs": ["mode"]},
    "Message":            {"desc": "A signalling message / PDU.", "subtype_of": "Entity", "attrs": []},
    "InformationElement": {"desc": "A field inside a message or another IE/header.", "subtype_of": "Entity", "attrs": ["presence", "needCode", "conditionalPresence"]},
    "Timer":              {"desc": "A protocol timer.", "subtype_of": "Entity", "attrs": ["value_domain"]},
    "State":              {"desc": "A UE state.", "subtype_of": "Entity", "attrs": []},
    "Event":              {"desc": "A trigger or failure event.", "subtype_of": "Entity", "attrs": []},
    "Condition":          {"desc": "A guarding condition on behaviour.", "subtype_of": "Entity", "attrs": []},
    "Capability":         {"desc": "A UE capability/feature.", "subtype_of": "Entity", "attrs": []},
    "Bearer":             {"desc": "A radio bearer (SRB/DRB/MRB).", "subtype_of": "Entity", "attrs": []},
    "UEVariable":         {"desc": "A named UE state store (Var...).", "subtype_of": "Entity", "attrs": []},
    "Release":            {"desc": "A 3GPP release; ordered via NEXT_RELEASE.", "subtype_of": "Entity", "attrs": []},

    # --- IMS additions (TS 24.229; SIP-based call control) ---
    "SIPMethod":          {"desc": "A SIP request method (REGISTER, INVITE, SUBSCRIBE, …).", "subtype_of": "Message", "attrs": []},
    "SIPResponse":        {"desc": "A SIP status response (200 OK, 401, 420, …).", "subtype_of": "Message", "attrs": ["code"]},
    "SIPHeader":          {"desc": "A SIP header field (P-Access-Network-Info, Service-Route, …).", "subtype_of": "InformationElement", "attrs": []},
    "Identity":           {"desc": "An IMS identity (public/private user identity, GRUU, …).", "subtype_of": "InformationElement", "attrs": []},
    "NetworkElement":     {"desc": "An IMS network function the UE interacts with (P-CSCF, S-CSCF, …).", "subtype_of": "Entity", "attrs": []},
}

# Domain entity types that get classified under a ProtocolLayer via IN_LAYER.
DOMAIN_ENTITY_TYPES = ["Procedure", "Message", "InformationElement", "Timer", "State",
                       "Event", "Condition", "Capability", "Bearer", "UEVariable",
                       "SIPMethod", "SIPResponse", "SIPHeader", "Identity", "NetworkElement"]

# ---------------------------------------------------------------------------
# Relationship types  (name -> {domain, range, desc, attrs})
# domain/range are checked **subtype-aware** (a from-type is OK if it is a
# subtype-or-equal of any listed domain type). ["*"] means "any".
#
# ``functional: True`` marks a type whose subject is expected to have ONE object
# (within a release): two different objects for the same (from, type) is a
# conflict candidate, and snapshot.conflict_groups routes the group to the
# review queue (KARMA CRA-derived, minus the LLM debate and minus the auto-drop
# — research doc 05 §2.7/§3.1). Most SAGE relations are legitimately
# multi-valued (a Procedure EXCHANGES many messages), so the flag is opt-in per
# type and, like the rest of the schema, an open seed (D-015) — extend it as
# evidence accumulates.
# ---------------------------------------------------------------------------
RELATIONSHIP_TYPES = {
    "DEFINED_IN":          {"domain": ["*"], "range": ["Clause"], "desc": "Entity's source/home clause (provenance).", "attrs": []},
    "CONTAINS":            {"domain": ["Message", "InformationElement"], "range": ["InformationElement"], "desc": "Structural containment (ASN.1 / SIP header set).", "attrs": ["presence"]},
    "HAS_DOMAIN":          {"domain": ["InformationElement"], "range": ["InformationElement", "Capability"], "desc": "IE's value domain / enumerated type.", "attrs": [], "functional": True},
    "EXCHANGES":           {"domain": ["Procedure"], "range": ["Message"], "desc": "Procedure sends/receives a message (incl. SIP request/response).", "attrs": ["direction"]},
    "REUSED_BY":           {"domain": ["Message"], "range": ["Procedure"], "desc": "Message is reused by another procedure.", "attrs": ["role"]},
    "STARTS":              {"domain": ["Procedure"], "range": ["Timer"], "desc": "Procedure starts a timer.", "attrs": []},
    "STOPS":               {"domain": ["Procedure"], "range": ["Timer"], "desc": "Procedure stops a timer.", "attrs": []},
    "TRANSITIONS_TO":      {"domain": ["Procedure"], "range": ["State"], "desc": "Procedure transitions the UE into a state.", "attrs": []},
    "HAS_PRECONDITION":    {"domain": ["Procedure"], "range": ["State", "Condition"], "desc": "Precondition for the procedure.", "attrs": []},
    "TRIGGERS":            {"domain": ["Event"], "range": ["Procedure"], "desc": "Event triggers a procedure.", "attrs": []},
    "ALTERNATIVE_OUTCOME": {"domain": ["Procedure"], "range": ["Message"], "desc": "Alternative (e.g. reject/error response) outcome.", "attrs": []},
    "ESTABLISHES":         {"domain": ["Procedure"], "range": ["Bearer"], "desc": "Procedure establishes a bearer.", "attrs": []},
    "INVOKES":             {"domain": ["Procedure"], "range": ["Procedure"], "desc": "Procedure invokes a sub-procedure (cross-reference).", "attrs": ["guard"]},
    "ON_EXPIRY_OF":        {"domain": ["Event"], "range": ["Timer"], "desc": "Event is the expiry of a timer.", "attrs": [], "functional": True},
    "CONFIGURES":          {"domain": ["InformationElement"], "range": ["Timer"], "desc": "IE delivers/configures a timer value.", "attrs": []},
    "GOVERNS":             {"domain": ["Timer"], "range": ["Procedure"], "desc": "Timer supervises a procedure.", "attrs": [], "functional": True},
    # Range widened from UEVariable-only (2026-07-19, D-015 additive): the full
    # TS 38.331 run produced 609 range violations (28% of all its errors) from
    # procedures reading/writing IE *fields*, not just UE variables — "the UE
    # shall set the <IE> to ..." is ordinary spec prose. The narrow range came
    # from a 2-clause pilot where only variables happened to appear; it was a
    # sampling artefact, not a claim that procedures never touch IEs.
    "READS":               {"domain": ["Procedure"], "range": ["UEVariable", "InformationElement"], "desc": "Procedure reads a UE variable or IE field.", "attrs": []},
    "WRITES":              {"domain": ["Procedure"], "range": ["UEVariable", "InformationElement"], "desc": "Procedure writes a UE variable or IE field.", "attrs": []},
    "ACTS_ON":             {"domain": ["Procedure"], "range": ["ProtocolLayer"], "desc": "Procedure acts on another layer's entity.", "attrs": ["cross-spec"]},
    "ON_FAILURE_INVOKES":  {"domain": ["Procedure"], "range": ["Procedure"], "desc": "On failure, procedure invokes another.", "attrs": ["guard"]},
    # IMS additions
    "INTERACTS_WITH":      {"domain": ["Procedure"], "range": ["NetworkElement"], "desc": "UE procedure interacts with an IMS network element.", "attrs": ["role"]},
    "IDENTIFIED_BY":       {"domain": ["Procedure", "Message"], "range": ["Identity"], "desc": "Procedure/message carries or asserts an IMS identity.", "attrs": []},
    # concept-scheme links
    "IN_LAYER":            {"domain": DOMAIN_ENTITY_TYPES, "range": ["ProtocolLayer"], "desc": "Classifies a domain entity under its protocol layer.", "attrs": []},
    "BROADER":             {"domain": ["ProtocolLayer", "Stratum"], "range": ["Stratum", "DomainRoot"], "desc": "SKOS broader within the concept scheme.", "attrs": []},
    # versioning (D-011)
    "NEXT_RELEASE":        {"domain": ["Release"], "range": ["Release"], "desc": "Release ordering.", "attrs": []},
    "SUPERSEDES":          {"domain": ["*"], "range": ["*"], "desc": "A versioned assertion supersedes a prior one.", "attrs": []},
}


# ---------------------------------------------------------------------------
# Subtype-aware helpers
# ---------------------------------------------------------------------------
def subtypes_of(typ):
    """All descendant types of ``typ`` including itself."""
    out = {typ}
    changed = True
    while changed:
        changed = False
        for name, spec in ENTITY_TYPES.items():
            if spec["subtype_of"] in out and name not in out:
                out.add(name); changed = True
    return out


def is_a(typ, ancestor):
    """True if ``typ`` is ``ancestor`` or a subtype of it."""
    cur = typ
    while cur is not None:
        if cur == ancestor:
            return True
        spec = ENTITY_TYPES.get(cur)
        cur = spec["subtype_of"] if spec else None
    return False


def domain_range_ok(allowed, typ):
    """Subtype-aware membership: is ``typ`` a subtype-or-equal of any allowed type?

    ``allowed == ["*"]`` matches anything. ``Clause`` is a corpus pseudo-type
    (DEFINED_IN range) with no entity record, so it is matched literally.
    """
    if allowed == ["*"]:
        return True
    return any(typ == a or is_a(typ, a) for a in allowed)
