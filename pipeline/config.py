"""Per-spec configuration for the extraction pipeline.

A ``SpecConfig`` tells the pipeline where the corpus lives, how to address it
(spec/version/release), which ProtocolLayer concept its entities belong to, and
the UE-relevance hints for the filter (clause ranges + actor heuristics).

Releases shared across specs come from the ontology's release universe.
"""
from dataclasses import dataclass, field
from typing import List, Tuple

RELEASES = ["Rel-15", "Rel-16", "Rel-17", "Rel-18", "Rel-19"]


@dataclass(frozen=True)
class SpecConfig:
    spec: str                      # "TS 24.229"
    version: str                   # "19.6.0"
    store_dir: str                 # corpus/store/<...>
    layer_concept: str             # "C_IMS"
    # UE-relevance hints (used by ue_filter):
    ue_clause_prefixes: Tuple[str, ...] = ()      # clause-number prefixes that are UE-side
    drop_clause_prefixes: Tuple[str, ...] = ()    # prefixes to exclude (annexes, network-only)
    ue_actor_terms: Tuple[str, ...] = ()          # phrases marking UE-side normative text
    network_actor_terms: Tuple[str, ...] = ()     # phrases marking network-only text

    @property
    def release(self) -> str:
        return "Rel-%d" % int(self.version.split(".")[0])


# TS 24.229 — IMS call control (SIP/SDP). UE-side procedures live in clause 5.1
# (UE roles) and parts of clause 5.4 reuse; clause 6/7 are SDP/headers; clause B/L/etc
# are access-network annexes. The filter below is a *first cut* — refined against
# the actual corpus in ue_filter, then reviewed.
TS_24229 = SpecConfig(
    spec="TS 24.229",
    version="19.6.0",
    store_dir="corpus/store/24229-19.6.0",
    layer_concept="C_IMS",
    ue_clause_prefixes=("5.1",),                  # "Functions of the UA at the UE"
    drop_clause_prefixes=("_", "Annex", "Y", "Z"),
    ue_actor_terms=(
        "the UE shall", "the UE may", "the UE performs", "the UE sends",
        "upon receiving", "the UE includes", "when the UE", "the user agent",
    ),
    network_actor_terms=(
        "the P-CSCF shall", "the S-CSCF shall", "the I-CSCF shall",
        "the AS shall", "the BGCF shall", "the network shall",
    ),
)

REGISTRY = {(c.spec, c.version): c for c in (TS_24229,)}


def get(spec, version):
    return REGISTRY[(spec, version)]
