"""Per-spec configuration for the extraction pipeline.

A ``SpecConfig`` tells the pipeline how to address a spec (spec/version/release),
where its corpus store lives, which ProtocolLayer concept its entities belong to,
and the UE-relevance hints for the filter (clause ranges + actor heuristics).

The UE-relevance hints and layer are **properties of the spec, not the version** —
clause 5.1 is the UE's role in TS 24.229 whether you ingest Rel-17 or Rel-19. So
the registry holds one **version-independent template per spec**; ``get(spec,
version)`` stamps it with a concrete version and derives the store path. Any
version fetched by ``corpus/fetch_spec.py`` works without a new registry entry.
"""
import string
from dataclasses import dataclass, replace
from typing import Tuple

RELEASES = ["Rel-15", "Rel-16", "Rel-17", "Rel-18", "Rel-19", "Rel-20"]


@dataclass(frozen=True)
class SpecConfig:
    spec: str                      # "TS 24.229"
    version: str                   # "19.6.0"  (filled in by get(); "" in a template)
    layer_concept: str             # "C_IMS"
    # UE-relevance hints (used by ue_filter) — version-independent:
    ue_clause_prefixes: Tuple[str, ...] = ()      # clause-number prefixes that are UE-side
    drop_clause_prefixes: Tuple[str, ...] = ()    # prefixes to exclude (annexes, network-only)
    ue_actor_terms: Tuple[str, ...] = ()          # phrases marking UE-side normative text
    network_actor_terms: Tuple[str, ...] = ()     # phrases marking network-only text
    # Controlled vocabulary for the deterministic extractors (stage 2): pairs of
    # (entity_type, terms). A term appearing verbatim in a UE clause becomes a
    # high-precision entity of that type, anchored at its first occurrence. Terms
    # must be unambiguous tokens (message names, timer names, states, Var...) —
    # fuzzy/semantic naming is the LLM's + aligner's job, not vocab's.
    vocab: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()

    @property
    def compact(self) -> str:
        """'TS 24.229' -> '24229' (matches build_corpus.py's store key)."""
        return self.spec.replace("TS ", "").replace(".", "")

    @property
    def store_dir(self) -> str:
        """Corpus store for this exact version — same key build_corpus.py writes."""
        return "corpus/store/%s-%s" % (self.compact, self.version)

    @property
    def release(self) -> str:
        return "Rel-%d" % int(self.version.split(".")[0])


# Version-independent templates, keyed by spec. ``version`` stays "" here and is
# filled by get(). UE-relevance hints below describe the spec's structure, which
# is stable across releases (refined against the corpus in ue_filter, then reviewed).

# TS 24.229 — IMS call control (SIP/SDP). UE-side procedures live in clause 5.1
# ("Functions of the UA at the UE"); clause 6/7 are SDP/headers; annexes (B/L/…)
# are access-network specific.
_SIP_METHODS = ("REGISTER", "INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "SUBSCRIBE",
                "NOTIFY", "PUBLISH", "MESSAGE", "REFER", "INFO", "PRACK", "UPDATE")

_SIP_HEADERS = (
    "P-Access-Network-Info", "P-Preferred-Identity", "P-Asserted-Identity",
    "P-Associated-URI", "P-Called-Party-ID", "P-Visited-Network-ID",
    "P-Preferred-Service", "P-Asserted-Service", "P-Profile-Key",
    "Service-Route", "Path", "Contact", "Authorization", "WWW-Authenticate",
    "Security-Client", "Security-Verify", "Security-Server", "Require",
    "Proxy-Require", "Supported", "Route", "Privacy", "Feature-Caps",
    "Accept-Contact", "Reject-Contact", "Request-Disposition", "Expires",
)

_TS_24229 = SpecConfig(
    spec="TS 24.229",
    version="",
    layer_concept="C_IMS",
    ue_clause_prefixes=("5.1",),
    # Letter-keyed clauses are annexes (B/K/L/U… = access-technology-specific
    # UE procedures). Excluded from v1 scope — re-including them is a deliberate
    # future scope decision, not something the actor-term fallback should do.
    drop_clause_prefixes=("_",) + tuple(string.ascii_uppercase),
    ue_actor_terms=(
        "the UE shall", "the UE may", "the UE performs", "the UE sends",
        "upon receiving", "the UE includes", "when the UE", "the user agent",
    ),
    network_actor_terms=(
        "the P-CSCF shall", "the S-CSCF shall", "the I-CSCF shall",
        "the AS shall", "the BGCF shall", "the network shall",
    ),
    vocab=(("SIPMethod", _SIP_METHODS), ("SIPHeader", _SIP_HEADERS)),
)

# TS 38.331 — NR RRC. The whole spec is the UE's RRC protocol: clause 5 is the
# UE procedures ("the UE shall ..."), clause 7 the UE timers/counters/constants;
# clause 6 is the ASN.1 message syntax (deterministic ASN.1 parsing is a later,
# separate stage — not prose extraction) and 8/9/10+ are field descriptions /
# NB-IoT / annex material. Vocab terms are unambiguous camel-case message names,
# T-timers, RRC_ states and Var... UE variables, seeded from the hand-built RRC
# pilot (rrc-pilot/) plus the spec's own tables of the same kinds.
_TS_38331 = SpecConfig(
    spec="TS 38.331",
    version="",
    layer_concept="C_RRC",
    ue_clause_prefixes=("5.", "7."),
    drop_clause_prefixes=("_", "Annex", "?"),
    ue_actor_terms=(
        "the UE shall", "the UE may", "the UE performs", "upon reception",
        "when the UE", "if the UE",
    ),
    network_actor_terms=(
        "the network shall", "the gNB shall", "the ng-eNB shall",
    ),
    vocab=(
        ("Message", ("RRCSetupRequest", "RRCSetup", "RRCSetupComplete", "RRCReject",
                     "RRCReconfiguration", "RRCReconfigurationComplete",
                     "RRCReestablishmentRequest", "RRCReestablishment",
                     "RRCReestablishmentComplete", "RRCResumeRequest", "RRCResumeRequest1",
                     "RRCResume", "RRCResumeComplete", "RRCRelease",
                     "SecurityModeCommand", "SecurityModeComplete", "SecurityModeFailure",
                     "MeasurementReport", "UECapabilityEnquiry", "UECapabilityInformation",
                     "ULInformationTransfer", "DLInformationTransfer",
                     "FailureInformation", "UEAssistanceInformation", "SIB1")),
        ("Timer", ("T300", "T301", "T302", "T304", "T310", "T311", "T312", "T316",
                   "T319", "T320", "T321", "T325", "T331", "T380", "T390", "T420", "T430")),
        ("State", ("RRC_IDLE", "RRC_INACTIVE", "RRC_CONNECTED")),
        ("UEVariable", ("VarConditionalReconfig", "VarConnEstFailReport",
                        "VarLogMeasReport", "VarMeasConfig", "VarMeasReportList",
                        "VarMobilityHistoryReport", "VarRA-Report", "VarRLF-Report",
                        "VarResumeMAC-Input", "VarShortMAC-Input")),
        ("Bearer", ("SRB0", "SRB1", "SRB2", "SRB3")),
    ),
)

TEMPLATES = {t.spec: t for t in (_TS_24229, _TS_38331)}


def get(spec, version):
    """Return a SpecConfig for (spec, version), deriving the store path.

    The spec must have a registered template; any version is accepted (the store
    just has to exist on disk — rebuild it with corpus/fetch_spec.py).
    """
    tmpl = TEMPLATES.get(spec)
    if tmpl is None:
        raise KeyError("no SpecConfig template for %r (known: %s)"
                       % (spec, ", ".join(sorted(TEMPLATES)) or "none"))
    return replace(tmpl, version=version)
