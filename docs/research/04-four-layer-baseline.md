# Phase-0: Four-Layer Baseline (decision + first build)

**Status**: Decision agreed and realised 2026-06-06. Baseline for the whole project.
**Source slice**: TS 38.331 v19.2.0, RRC connection establishment (5.3.3) + reconfiguration (5.3.5).

## Decision: clean separation of four layers

Driven by the question "should 100% verbatim prose be part of the ontology/KG?" — answer: **no.**
The structured layers are selective; the complete text is a separate, linked layer.

1. **Corpus document store** — complete verbatim clause text (prose + ASN.1), addressable.
   100% coverage lives **here**.
2. **Taxonomy** — classification structure only: document spine (org + clause tree, titles, no
   body) + UE domain hierarchy (SKOS-style). No text.
3. **Ontology** (TBox) — entity types + relationship types with `domain → range` + attributes.
4. **Knowledge graph** (ABox) — instances + typed relationships, **text-free**, each with a
   provenance ref (`DEFINED_IN` / clause + anchor) resolving into the corpus.

Rationale (full reasoning in chat): structured layers are for *reasoning/traversal* (inherently
lossy, abstraction is the value); the corpus is for *retrieval of exact normative text* (verbatim,
100%). One artifact can't serve both success criteria. Losslessness is achieved by **linking** the
KG to the complete corpus, not by encoding prose as graph structure. For a normative spec where
exact wording is load-bearing (compliance/certification), this makes the corpus + provenance layer
unusually important — which argues *for* the separation, not against it. The right coverage metric
is: ~100% **text** coverage in the corpus, ~100% **conceptual** coverage (entities/relationships
vs. competency questions) in the ontology/KG. Chasing 100% *text* coverage in the ontology/KG is
the wrong metric for the wrong layer.

> Promote to `DECISIONS.md` as a `D-XXX` when we enter the architecture phase.

## Realisation (RRC pilot) — see `rrc-pilot/`

- **Single source of truth**: `rrc-pilot/rrc_model.py` (FACTS + ontology + domain taxonomy).
- **Compiler**: `rrc-pilot/build_layers.py` → corpus store, taxonomy, ontology, kg + validation.
- **View**: `corpus/viz/build_rrc_graph.py` now **consumes** `kg.json` + corpus store (no more
  duplicated data — the layers are authoritative).

### Build result (0 errors, 0 warnings)

- corpus: **1506 clauses** (38.331 v19.2.0), verbatim, addressable.
- taxonomy: document spine (1508 nodes) + domain (12 concepts).
- ontology: **11 entity types, 20 relationship types** (with domain/range).
- kg: **44 entities, 51 relations**, all text-free with resolving provenance.

### Validation performed by the build

- **KG ⊨ ontology**: every entity/relationship type declared; every relation's `from`/`to`
  obeys the declared `domain`/`range`. (0 violations.)
- **KG ⊨ corpus**: every provenance clause resolves; every anchor locates in that clause's text
  (incl. named ASN.1 sub-units). (0 unresolved.)

## Finding: 3GPP clause-6 structure

Clause 6 (ASN.1) organises each message/IE under a named `– <Name>` pseudo-heading rather than a
dotted number. Naïve dotted-number keying collapsed them (739 vs 1508). The corpus now captures
named units as keys like `6.2.2/RRCSetupRequest`, so message provenance points at the exact ASN.1
definition. (Precise ASN.1 *field*-level anchoring still needs a real ASN.1 parser — future work.)

## Store-agnostic

All layers are plain JSON — deliberately neutral on the deferred RDF/SKOS-vs-property-graph store
decision. They load into either later.

## Next

- Pilot 2 (IMS, TS 24.229): re-run the same four-layer build on a prose-only spec (no ASN.1
  backbone) — the real stress test of the corpus/KG split and behavioural extraction.
- When the schema stabilises across RRC+IMS, promote the layer-separation + seed schema to
  `DECISIONS.md` and pick the production store.
