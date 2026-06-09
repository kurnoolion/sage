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
from dataclasses import dataclass, replace
from typing import Tuple

RELEASES = ["Rel-15", "Rel-16", "Rel-17", "Rel-18", "Rel-19"]


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
_TS_24229 = SpecConfig(
    spec="TS 24.229",
    version="",
    layer_concept="C_IMS",
    ue_clause_prefixes=("5.1",),
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

TEMPLATES = {t.spec: t for t in (_TS_24229,)}


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
