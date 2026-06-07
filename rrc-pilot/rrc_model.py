"""Canonical source data for the RRC pilot — the single source of truth.

`build_layers.py` compiles this (plus the docx corpus) into the four separated
layers (corpus / taxonomy / ontology / knowledge-graph). The visualization is a
*consumer* of the compiled layers, not a second source of truth.

Nothing here is executed at import beyond defining data structures.
"""

SPEC = "TS 38.331"
VERSION = "19.2.0"
RELEASE = "Rel-19"
SOURCE_FILE = "38331-j20.docx"

# ---------------------------------------------------------------------------
# ONTOLOGY (TBox) — entity types and relationship types with domain->range.
# ---------------------------------------------------------------------------
# Entity-type hierarchy (the *taxonomy* of types) now lives inside the ontology
# via `subtype_of`. `Entity` is the root; `DomainRoot`/`Stratum`/`ProtocolLayer`
# are the structural types whose instances form the domain concept scheme.
ENTITY_TYPES = {
    "Entity":             {"desc": "Root of the entity-type hierarchy.", "subtype_of": None, "attrs": []},
    "DomainRoot":         {"desc": "Top of the domain concept scheme (the UE).", "subtype_of": "Entity", "attrs": []},
    "Stratum":            {"desc": "A protocol stratum (Access / Non-Access).", "subtype_of": "Entity", "attrs": []},
    "ProtocolLayer":      {"desc": "A protocol-stack layer (RRC, MAC, RLC, PDCP, SDAP, PHY, NAS-MM/SM, IMS).", "subtype_of": "Entity", "attrs": []},
    "Procedure":          {"desc": "A UE behavioural procedure defined in a clause.", "subtype_of": "Entity", "attrs": ["mode"]},
    "Message":            {"desc": "A signalling message (PDU).", "subtype_of": "Entity", "attrs": []},
    "InformationElement": {"desc": "A field inside a message or another IE.", "subtype_of": "Entity", "attrs": ["presence", "needCode", "conditionalPresence"]},
    "Timer":              {"desc": "A protocol timer (Txxx).", "subtype_of": "Entity", "attrs": ["value_domain"]},
    "State":              {"desc": "A UE RRC state.", "subtype_of": "Entity", "attrs": []},
    "Event":              {"desc": "A trigger or failure event (e.g. timer expiry, upper-layer request).", "subtype_of": "Entity", "attrs": []},
    "Condition":          {"desc": "A guarding condition on behaviour.", "subtype_of": "Entity", "attrs": []},
    "Capability":         {"desc": "A UE capability/feature.", "subtype_of": "Entity", "attrs": []},
    "Bearer":             {"desc": "A radio bearer (SRB/DRB/MRB).", "subtype_of": "Entity", "attrs": []},
    "UEVariable":         {"desc": "A named UE state store (Var...).", "subtype_of": "Entity", "attrs": []},
    "Release":            {"desc": "A 3GPP release (Rel-15…); ordered via NEXT_RELEASE.", "subtype_of": "Entity", "attrs": []},
}

# Release universe we plan to ingest (ordered). cur = derived from the spec version.
RELEASES = ["Rel-15", "Rel-16", "Rel-17", "Rel-18", "Rel-19"]
# Lifecycle fields stamped on every entity & relation (see D-011):
#   observed_in: [Release]   releases we've actually ingested this fact from
#   introduced_in: Release|None   (None = unknown until earlier releases land)
#   valid_until: Release|None      (None = still current)
#   supersedes: id|None            (for versioned/changed assertions)

# Domain entity types that get classified under a ProtocolLayer via IN_LAYER.
DOMAIN_ENTITY_TYPES = ["Procedure", "Message", "InformationElement", "Timer",
                       "State", "Event", "Condition", "Capability", "Bearer", "UEVariable"]

# relationship type -> (domain types, range types, description, allowed attrs)
RELATIONSHIP_TYPES = {
    "DEFINED_IN":         (["*"], ["Clause"], "Entity's source/home clause (provenance).", []),
    "CONTAINS":           (["Message", "InformationElement"], ["InformationElement"], "Structural containment (from ASN.1).", ["presence"]),
    "HAS_DOMAIN":         (["InformationElement"], ["InformationElement", "Capability"], "IE's value domain / enumerated type.", []),
    "EXCHANGES":          (["Procedure"], ["Message"], "Procedure sends/receives a message.", ["direction"]),
    "REUSED_BY":          (["Message"], ["Procedure"], "Message is reused by another procedure.", ["role"]),
    "STARTS":             (["Procedure"], ["Timer"], "Procedure starts a timer.", []),
    "STOPS":              (["Procedure"], ["Timer"], "Procedure stops a timer.", []),
    "TRANSITIONS_TO":     (["Procedure"], ["State"], "Procedure transitions the UE into a state.", []),
    "HAS_PRECONDITION":   (["Procedure"], ["State", "Condition"], "Precondition for the procedure.", []),
    "TRIGGERS":           (["Event"], ["Procedure"], "Event triggers a procedure.", []),
    "ALTERNATIVE_OUTCOME":(["Procedure"], ["Message"], "Alternative (e.g. reject) outcome.", []),
    "ESTABLISHES":        (["Procedure"], ["Bearer"], "Procedure establishes a bearer.", []),
    "INVOKES":            (["Procedure"], ["Procedure"], "Procedure invokes a sub-procedure.", ["guard"]),
    "ON_EXPIRY_OF":       (["Event"], ["Timer"], "Event is the expiry of a timer.", []),
    "CONFIGURES":         (["InformationElement"], ["Timer"], "IE delivers/configures a timer value.", []),
    "GOVERNS":            (["Timer"], ["Procedure"], "Timer supervises a procedure.", []),
    "READS":              (["Procedure"], ["UEVariable"], "Procedure reads a UE variable.", []),
    "WRITES":             (["Procedure"], ["UEVariable"], "Procedure writes a UE variable.", []),
    "ACTS_ON":            (["Procedure"], ["ProtocolLayer"], "Procedure acts on another layer's entity.", ["cross-spec"]),
    "ON_FAILURE_INVOKES": (["Procedure"], ["Procedure"], "On failure, procedure invokes another.", ["guard"]),
    # links to the domain concept scheme
    "IN_LAYER":           (DOMAIN_ENTITY_TYPES, ["ProtocolLayer"], "Classifies a domain entity under its protocol layer.", []),
    "BROADER":            (["ProtocolLayer", "Stratum"], ["Stratum", "DomainRoot"], "SKOS broader within the concept scheme.", []),
    # versioning (D-011)
    "NEXT_RELEASE":       (["Release"], ["Release"], "Release ordering (Rel-N → Rel-N+1).", []),
    "SUPERSEDES":         (["*"], ["*"], "A versioned assertion supersedes a prior one.", []),
}

# ---------------------------------------------------------------------------
# DOMAIN CONCEPT SCHEME (DCS) — curated SKOS-style scheme of the UE protocol
# stack. Each concept is also a KG instance of its ontology `type`. Concept ids
# are prefixed "C_" so they never collide with extracted-entity ids.
# id -> (label, ontology type, broader concept id, in_scope)
# ---------------------------------------------------------------------------
CONCEPT_SCHEME = "UE-protocol-domain"
CONCEPTS = {
    "C_UE":   ("User Equipment", "DomainRoot", None, True),
    "C_AS":   ("Access Stratum", "Stratum", "C_UE", True),
    "C_NAS":  ("Non-Access Stratum", "Stratum", "C_UE", True),
    "C_RRC":  ("Radio Resource Control", "ProtocolLayer", "C_AS", True),
    "C_PDCP": ("Packet Data Convergence Protocol", "ProtocolLayer", "C_AS", True),
    "C_RLC":  ("Radio Link Control", "ProtocolLayer", "C_AS", True),
    "C_MAC":  ("Medium Access Control", "ProtocolLayer", "C_AS", True),
    "C_SDAP": ("Service Data Adaptation Protocol", "ProtocolLayer", "C_AS", False),
    "C_PHY":  ("Physical layer", "ProtocolLayer", "C_AS", False),
    "C_NAS-MM": ("NAS Mobility Management", "ProtocolLayer", "C_NAS", False),
    "C_NAS-SM": ("NAS Session Management", "ProtocolLayer", "C_NAS", False),
    "C_IMS":  ("IP Multimedia Subsystem", "ProtocolLayer", "C_NAS", False),
}

# Map a spec to the ProtocolLayer concept its entities belong to (for IN_LAYER).
SPEC_LAYER = {"TS 38.331": "C_RRC"}

# Document-taxonomy organisational chain (above the clause tree, which is
# extracted from the docx at build time).
ORG = {
    "sdo": "3GPP",
    "tsg": "TSG RAN",
    "working_group": "RAN2",
    "series": "38",
    "spec": SPEC, "version": VERSION, "release": RELEASE,
    "spec_title": "NR; Radio Resource Control (RRC); Protocol specification",
}

# ---------------------------------------------------------------------------
# KNOWLEDGE-GRAPH instances (ABox).
# entity id -> (label, type, home_clause, display_gloss)
# display_gloss is for the *viz only*; it is stripped from kg.json.
# home_clause: "TS 38.321"-style value means defined in another spec (external).
# ---------------------------------------------------------------------------
ENTITIES = {
 "P_setup":      ("RRC connection establishment","Procedure","5.3.3",
   "Establish an RRC connection; involves SRB1 establishment; transfers initial NAS dedicated info UE->NW."),
 "P_reconfig":   ("RRC reconfiguration","Procedure","5.3.5",
   "Modify an RRC connection: RBs, reconfiguration with sync, measurements, SCells/cell groups, conditional reconfig."),
 "P_cellgroup":  ("Cell group configuration","Procedure","5.3.5.5","Configure a cell group (shared sub-procedure)."),
 "P_rbconfig":   ("Radio bearer configuration","Procedure","5.3.5.6","Configure radio bearers (shared sub-procedure)."),
 "P_seckey":     ("AS security key update","Procedure","5.3.5.7","Update AS security keys."),
 "P_uac":        ("Unified access control","Procedure","5.3.14","Access-control check before connection attempt."),
 "P_measconfig": ("Measurement configuration","Procedure","5.5.2","Configure measurements."),
 "P_condreconfig":("Conditional reconfiguration","Procedure","5.3.5.13","Configure/evaluate/execute conditional (CHO/CPA/CPC) reconfig."),
 "P_reest":      ("RRC connection re-establishment","Procedure","5.3.7","Re-establish an RRC connection."),
 "P_scgfail":    ("SCG failure information","Procedure","5.7.3","Report SCG failure."),
 "M_setupreq":   ("RRCSetupRequest","Message","6.2.2/RRCSetupRequest","CCCH UL message starting establishment."),
 "M_setup":      ("RRCSetup","Message","6.2.2/RRCSetup","NW->UE setup message carrying radioBearerConfig + masterCellGroup."),
 "M_setupcomplete":("RRCSetupComplete","Message","6.2.2/RRCSetupComplete","UE->NW completion carrying NAS + PLMN selection."),
 "M_reject":     ("RRCReject","Message","6.2.2/RRCReject","NW->UE reject of a setup request."),
 "M_reconfig":   ("RRCReconfiguration","Message","6.2.2/RRCReconfiguration","NW->UE reconfiguration container."),
 "M_reconfigcomplete":("RRCReconfigurationComplete","Message","6.2.2/RRCReconfigurationComplete","UE->NW reconfiguration completion."),
 "IE_ueid":      ("ue-Identity","InformationElement","6.2.2","InitialUE-Identity in RRCSetupRequest."),
 "IE_estcause":  ("establishmentCause","InformationElement","6.2.2","EstablishmentCause enumerated."),
 "IE_rbconfig":  ("radioBearerConfig","InformationElement","6.2.2","RadioBearerConfig."),
 "IE_mastercg":  ("masterCellGroup","InformationElement","6.2.2","CellGroupConfig for the MCG."),
 "IE_secondarycg":("secondaryCellGroup","InformationElement","6.2.2","CellGroupConfig for the SCG."),
 "IE_measconfig":("measConfig","InformationElement","6.2.2","MeasConfig."),
 "IE_selplmn":   ("selectedPLMN-Identity","InformationElement","6.2.2","Selected PLMN index."),
 "IE_nasmsg":    ("dedicatedNAS-Message","InformationElement","6.2.2","Container for a NAS message."),
 "IE_reconfigwithsync":("reconfigurationWithSync","InformationElement","6.3.2","Reconfiguration-with-sync (handover) parameters."),
 "IE_t304":      ("t304","InformationElement","6.3.2","Enumerated T304 value carried in the message."),
 "IE_masterkeyupdate":("masterKeyUpdate","InformationElement","6.3.2","Triggers AS security key update."),
 "IE_condreconfig":("conditionalReconfiguration","InformationElement","6.3.2","Conditional reconfiguration IE."),
 "T_t300":("T300","Timer","5.3.3","Supervises RRC connection establishment."),
 "T_t390":("T390","Timer","5.3.3.4","Access-barring timer (stopped on setup)."),
 "T_t302":("T302","Timer","5.3.3.4","Access-barring timer (stopped on setup)."),
 "T_t304":("T304","Timer","5.3.5","Supervises reconfiguration with sync."),
 "T_t420":("T420","Timer","5.3.5.8.3","Supervises path switch."),
 "S_idle":("RRC_IDLE","State","4.2.1","Idle state."),
 "S_connected":("RRC_CONNECTED","State","4.2.1","Connected state."),
 "B_srb1":("SRB1","Bearer","4.2.2","Signalling radio bearer 1."),
 "E_ullreq":("Upper-layer establishment request","Event","5.3.3.2","Upper layers request an RRC connection."),
 "E_t300exp":("T300 expiry","Event","5.3.3.7","T300 expiry event."),
 "E_t304exp":("T304 expiry","Event","5.3.5.8.3","T304 expiry (reconfiguration with sync failure)."),
 "V_condreconfig":("VarConditionalReconfig","UEVariable","5.3.5.13","UE store of conditional reconfigurations."),
 "C_assec":("AS security activated","Condition","5.3.5.2","AS security has been activated."),
}
# Note: the layers acted upon (MAC/RLC/PDCP) are the DCS concepts C_MAC/C_RLC/C_PDCP,
# not separate entities — see CONCEPTS above.

# Relationship instances:
# (from, to, rel, modality, confidence, clause, proc, attrs_str, quote_anchor)
FACTS = [
 ("E_ullreq","P_setup","TRIGGERS","prose","med","5.3.3.2","estab","",
   "The UE initiates the procedure when upper layers request establishment of an RRC connection while the UE is in RRC_IDLE and it has acquired essential system information."),
 ("P_setup","S_idle","HAS_PRECONDITION","prose","med","5.3.3.2","estab","",
   "while the UE is in RRC_IDLE and it has acquired essential system information"),
 ("P_setup","M_setupreq","EXCHANGES","prose","high","5.3.3.2","estab","direction: UE->NW",
   "initiate transmission of the RRCSetupRequest message in accordance with 5.3.3.3"),
 ("P_setup","M_setup","EXCHANGES","prose","high","5.3.3.4","estab","direction: NW->UE",
   "The UE shall perform the following actions upon reception of the RRCSetup"),
 ("P_setup","M_setupcomplete","EXCHANGES","prose","high","5.3.3.4","estab","direction: UE->NW",
   "set the content of RRCSetupComplete message as follows"),
 ("P_setup","M_reject","ALTERNATIVE_OUTCOME","prose","med","5.3.3.1","estab","",
   "Figure 5.3.3.1-2: RRC connection establishment, network reject"),
 ("P_setup","T_t300","STARTS","prose","high","5.3.3.2","estab","","start timer T300"),
 ("P_setup","B_srb1","ESTABLISHES","prose","high","5.3.3.1","estab","",
   "RRC connection establishment involves SRB1 establishment"),
 ("P_setup","S_connected","TRANSITIONS_TO","prose","high","5.3.3.4","estab","","enter RRC_CONNECTED"),
 ("P_setup","T_t300","STOPS","prose","high","5.3.3.4","estab","","stop timer T300, T301, T319"),
 ("P_setup","T_t390","STOPS","prose","high","5.3.3.4","estab","","stop timer T390 for all access categories"),
 ("P_setup","T_t302","STOPS","prose","high","5.3.3.4","estab","","stop timer T302"),
 ("P_setup","P_uac","INVOKES","prose","high","5.3.3.2","estab","",
   "perform the unified access control procedure as specified in 5.3.14"),
 ("P_setup","P_cellgroup","INVOKES","prose","high","5.3.3.4","estab","guard: presence of masterCellGroup",
   "perform the cell group configuration procedure in accordance with the received masterCellGroup and as specified in 5.3.5.5"),
 ("P_setup","P_rbconfig","INVOKES","prose","high","5.3.3.4","estab","guard: presence of radioBearerConfig",
   "perform the radio bearer configuration procedure in accordance with the received radioBearerConfig and as specified in 5.3.5.6"),
 ("M_setupreq","IE_ueid","CONTAINS","asn1","high","6.2.2","estab","","ue-Identity"),
 ("M_setupreq","IE_estcause","CONTAINS","asn1","high","6.2.2","estab","","establishmentCause"),
 ("M_setup","IE_rbconfig","CONTAINS","asn1","high","6.2.2","estab","","radioBearerConfig"),
 ("M_setup","IE_mastercg","CONTAINS","asn1","high","6.2.2","estab","","masterCellGroup"),
 ("M_setupcomplete","IE_selplmn","CONTAINS","asn1","high","6.2.2","estab","","selectedPLMN-Identity"),
 ("M_setupcomplete","IE_nasmsg","CONTAINS","asn1","high","6.2.2","estab","","dedicatedNAS-Message"),
 ("M_setup","P_reest","REUSED_BY","prose","high","5.3.7.8","shared","role: re-establishment fallback",
   "Reception of the RRCSetup by the UE"),
 ("E_t300exp","T_t300","ON_EXPIRY_OF","prose","high","5.3.3.7","estab","","if timer T300 expires:"),
 ("P_reconfig","S_connected","HAS_PRECONDITION","prose","med","5.3.5.2","reconf","",
   "The Network may initiate the RRC reconfiguration procedure to a UE in RRC_CONNECTED"),
 ("P_reconfig","M_reconfig","EXCHANGES","prose","high","5.3.5.3","reconf","direction: NW->UE",
   "The UE shall perform the following actions upon reception of the RRCReconfiguration"),
 ("P_reconfig","M_reconfigcomplete","EXCHANGES","prose","high","5.3.5.3","reconf","direction: UE->NW",
   "RRCReconfigurationComplete"),
 ("M_reconfig","IE_rbconfig","CONTAINS","asn1","high","6.2.2","reconf","presence: Need M","radioBearerConfig"),
 ("M_reconfig","IE_secondarycg","CONTAINS","asn1","high","6.2.2","reconf","presence: Cond SCG","secondaryCellGroup"),
 ("M_reconfig","IE_measconfig","CONTAINS","asn1","high","6.2.2","reconf","presence: Need M","measConfig"),
 ("M_reconfig","IE_mastercg","CONTAINS","prose","med","5.3.5.3","reconf","presence-referenced",
   "if the RRCReconfiguration includes the masterCellGroup"),
 ("M_reconfig","IE_masterkeyupdate","CONTAINS","prose","med","5.3.5.3","reconf","presence-referenced",
   "if the RRCReconfiguration includes the masterKeyUpdate"),
 ("M_reconfig","IE_condreconfig","CONTAINS","prose","med","5.3.5.3","reconf","presence-referenced",
   "if the RRCReconfiguration includes the conditionalReconfiguration"),
 ("IE_mastercg","IE_reconfigwithsync","CONTAINS","asn1","high","6.3.2","reconf","",
   "reconfigurationWithSync"),
 ("IE_reconfigwithsync","IE_t304","CONTAINS","asn1","high","6.3.2","reconf","","t304"),
 ("IE_t304","T_t304","CONFIGURES","asn1","high","6.3.2","reconf","","t304"),
 ("T_t304","P_reconfig","GOVERNS","prose","high","5.3.5.8.3","reconf","","T304 expiry (Reconfiguration with sync Failure)"),
 ("E_t304exp","T_t304","ON_EXPIRY_OF","prose","high","5.3.5.8.3","reconf","","T304 of the MCG expires"),
 ("T_t420","P_reconfig","GOVERNS","prose","med","5.3.5.8.3","reconf","","if T420 expires"),
 ("P_reconfig","P_cellgroup","INVOKES","prose","high","5.3.5.3","reconf","guard: presence of masterCellGroup",
   "if the RRCReconfiguration includes the masterCellGroup"),
 ("P_reconfig","P_rbconfig","INVOKES","prose","high","5.3.5.3","reconf","guard: presence of radioBearerConfig",
   "if the RRCReconfiguration message includes the radioBearerConfig"),
 ("P_reconfig","P_seckey","INVOKES","prose","high","5.3.5.3","reconf","guard: presence of masterKeyUpdate",
   "if the RRCReconfiguration includes the masterKeyUpdate"),
 ("P_reconfig","P_measconfig","INVOKES","prose","high","5.3.5.3","reconf","guard: presence of measConfig",
   "if the RRCReconfiguration message includes the measConfig"),
 ("P_reconfig","P_condreconfig","INVOKES","prose","high","5.3.5.13.1","reconf","guard: presence of conditionalReconfiguration",
   "based on a received ConditionalReconfiguration IE"),
 ("P_condreconfig","V_condreconfig","WRITES","prose","high","5.3.5.3","reconf","",
   "remove all the entries in the condReconfigList within the MCG and the SCG VarConditionalReconfig"),
 ("P_condreconfig","V_condreconfig","READS","prose","high","5.3.5.13.1","reconf","",
   "the UE maintains two independent VarConditionalReconfig"),
 ("P_reconfig","C_RLC","ACTS_ON","prose","med","5.3.5.3","reconf","cross-spec: TS 38.322",
   "release the RLC entity or entities as specified in TS 38.322"),
 ("P_reconfig","C_PDCP","ACTS_ON","prose","med","5.3.5.3","reconf","cross-spec: TS 38.323",
   "reconfigure the PDCP entity to release DAPS as specified in TS 38.323"),
 ("P_reconfig","C_MAC","ACTS_ON","prose","med","5.3.5.3","reconf","cross-spec: TS 38.321",
   "reset the source MAC and release the source MAC configuration"),
 ("P_reconfig","C_assec","HAS_PRECONDITION","prose","med","5.3.5.2","reconf","",
   "is performed only when AS security has been activated"),
 ("P_reconfig","P_scgfail","ON_FAILURE_INVOKES","prose","high","5.3.5.8.2","reconf","guard: inability to comply (SRB3)",
   "initiate the SCG failure information procedure as specified in clause 5.7.3"),
 ("P_reconfig","P_reest","ON_FAILURE_INVOKES","prose","high","5.3.5.8.2","reconf","guard: inability to comply (MCG)",
   "initiate the connection re-establishment procedure as specified in"),
]
