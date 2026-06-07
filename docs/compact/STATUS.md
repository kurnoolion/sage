# Status

**Active phase**: requirements
**Last updated**: 2026-06-05

> **Note**: Project is in an informal **phase-0 research** mode (pre-requirements) — exploring
> 3GPP spec organization to design the UE taxonomy/ontology before formalizing requirements.
> Research artifacts live in `docs/research/` (outside the COMPACT state files).

## Done

- 2026-06-05 Project-init scaffold + imported Gemini design conversation as a design input.
- 2026-06-05 Phase-0 literature review of 3GPP/telecom taxonomy/ontology/KG work (`docs/research/01-...`).
- 2026-06-05 Agreed taxonomy approach D1–D4: two hierarchies (document + domain) joined by `DEFINED_IN`; UE-relevance filter; build order.
- 2026-06-05 Pilot 1 — RRC connection establishment modeled end-to-end from TS 38.331 v19.2.0 (`docs/research/02-...`); produced a candidate seed schema (TBox).
- 2026-06-05 Pilot 1b — RRC reconfiguration (5.3.5) modeled (`docs/research/03-...`); schema grew: ＋`UEVariable` entity, ＋`CONFIGURES`/`ON_FAILURE_INVOKES`/`READS`/`WRITES`/`ACTS_ON` relationships, ＋IE presence + INVOKES-guard attributes; sharpened the (asymmetric) granularity principle.
- 2026-06-05 Built interactive RRC graph visualization (entities/relationships + grounding spec text) at `corpus/viz/rrc-graph.html` (gitignored — embeds 3GPP text).
- 2026-06-06 Agreed **four-layer separation** (corpus / taxonomy / ontology / KG) and built+validated it for the RRC pilot under `rrc-pilot/` (0 errors, 0 warnings). Viz refactored to consume the layers (`docs/research/04-...`).
- 2026-06-06 Clarified to **3 layers + adjuncts**: taxonomy folds into the ontology (entity-type hierarchy via `subtype_of`); document taxonomy becomes the **corpus index**; added a curated **domain concept scheme** (SKOS) connected via `IN_LAYER` (entity→layer) + `BROADER`. Rebuilt 0/0: ontology 14 types/22 relations, KG 53 entities (incl. 12 concepts)/103 relations. Viz shows concepts behind a toggle.
- 2026-06-06 Built a **generic, data-driven KG viewer** (`rrc-pilot/viz/build_kg_view.py`, committable; HTML output gitignored) wired into `build_layers.py`. Colours/focus derived from ontology+data; toggles for corpus clauses + concept scheme; **highlights nodes/edges new since last view** (localStorage) + stats panel — for incremental inspection as the KG grows. Workflow: rebuild → refresh tab.
- 2026-06-07 Added a dedicated **domain-hierarchy (concept scheme) view** (`viz/build_concept_view.py`) — top-down `BROADER` tree, each concept annotated with its `IN_LAYER` entity count + v1-scope shading; wired into the build. README now explains all three hierarchies (type→ontology, domain→concept-scheme, document→corpus-index) with examples.

## In progress

- **Pilot 2 (IMS, TS 24.229 v19.6.0)** — started 2026-06-07. **Entire content ingested into the corpus**: 2096 clauses, all 488 tables captured, 6.0 MB verbatim (`corpus/store/24229-19.6.0/`, gitignored) + document hierarchy. Added spec-agnostic `corpus/build_corpus.py` (walks body incl. tables). KG extraction approach + scope TBD (see Flags). Ontology will need IMS-specific types (NetworkElement, SIPMethod, SIPHeader, …).
- Phase-0 schema validation — seed schema (now 14 entity types, 22 relationship types) formalized as `rrc-pilot/ontology/ontology.json`; agreed **extensible**. Open question: procedure modes vs. variants (research doc 03 §4).

## Next

- Pilot 2: **IMS** (TS 24.229) — re-run the four-layer build on a prose-only spec (no ASN.1 anchor); tests the corpus/KG split + behavioral-edge discipline without a deterministic backbone.
- When schema stabilizes across RRC+IMS: promote four-layer separation + seed schema to `DECISIONS.md`; pick production store (RDF/SKOS vs property graph).
- Then promote D1–D4 + the seed schema into `DECISIONS.md` and populate `PROJECT.md` / `requirements.md` (formal `/switch-phase requirements`).

## Flags

- Stakeholder map deferred — no domain-validator or eval-data channel named yet (v1 risk).
- Store choice (RDF/SKOS vs. property graph) unresolved — architecture-phase `D-XXX`; model so far is store-agnostic.
- Schema (entity/relationship types) is an **open/extensible seed** — expected to grow per spec; avoid premature closure.
- Layer-D validation (validating LLM-extracted behavioral triples without exhaustive human review) is the key unsolved problem inherited from prior work.
