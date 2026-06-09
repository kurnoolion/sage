# Status

**Active phase**: requirements
**Last updated**: 2026-06-08

> **Note**: Formally still pre-requirements; work has moved into design/architecture. The three-layer
> architecture is built + validated only on the **RRC pilot** (TS 38.331, clauses 5.3.3 + 5.3.5 — a
> deliberately small schema/method validation, not complete). For **IMS** (TS 24.229) only the raw
> **corpus** is ingested — no taxonomy/ontology/KG yet (that's the upcoming D-010 extraction pipeline).
> Decisions D-001…D-014 recorded. Research artifacts live in `docs/research/` (outside the COMPACT state files).

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
- 2026-06-07 Ingested the raw TS 24.229 (IMS) **corpus** — 2096 clauses + 488 tables, 6.0 MB verbatim (`corpus/store/24229-19.6.0/`, gitignored); added spec-agnostic `corpus/build_corpus.py` (walks body incl. tables). **Corpus only — no IMS taxonomy/ontology/KG yet.**
- 2026-06-07 Recorded **D-001…D-011** in `DECISIONS.md`. Baked **multi-release fields** (D-011) into the schema: `Release` entity type + `NEXT_RELEASE`/`SUPERSEDES`; every entity/relation stamped `observed_in`/`introduced_in`/`valid_until`/`supersedes` (now `Rel-19`); validation extended. Rebuilt 0/0.
- 2026-06-07 Re-keyed KG ids to a deterministic namespaced scheme (`3gpp:<layer>/<type>/<name>`); captured id-alignment + requirement-delta model in the scratchpad.
- 2026-06-07 Recorded **D-012** (change-tracking/derivation) + **D-013** (NORA integration contract) after a grounded NORA deep-read; added a **risk register (R1–R14)** + post-ingestion risk-auditor design (scratchpad §I); captured open D-013 contract TODOs (§H.15).
- 2026-06-08 Removed Claude co-author from all commit history; recorded the no-co-author preference.
- 2026-06-08 Named the project **SAGE** (Specification-Anchored Graph of Entities) — **D-014**; rebranded docs; renamed dir + GitHub repo `3gpp-kg` → `sage`.

## In progress

- **D-013 NORA integration contract** — drafted; **9 open contract TODOs** remain (scratchpad §H.15: inbound manifest, outbound artifacts, per-release projection API, representative-version table, feature crosswalk, base-assertion id, overlay form, tier-2 edges, update cadence).
- Seed schema: **15 entity types / 24 relationship types** (release + concept-scheme aware) in `rrc-pilot/ontology/ontology.json`; agreed **extensible**. Open question: procedure modes vs. variants (research doc 03 §4).

## Next

- **Decision point**: close the **[now] D-013 contract items** (§H.15) OR build the **D-010 extraction pipeline** (gold seed → few-shot prompt → local-model extraction → validation → review queue) — the latter is the path to the first **IMS** taxonomy/ontology/KG (can't hand-author a 1000-page prose spec).
- Build the **post-ingestion risk auditor** (**D-016**; scratchpad §I, R1–R14).
- Formalize: `/switch-phase architecture`; when schema stabilizes across RRC+IMS, pick the production store (RDF/SKOS vs property graph).

## Flags

- Stakeholder map deferred — no domain-validator or eval-data channel named yet (v1 risk).
- Store choice (RDF/SKOS vs. property graph) unresolved — architecture-phase `D-XXX`; model so far is store-agnostic.
- Schema (entity/relationship types) is an **open/extensible seed** — expected to grow per spec; avoid premature closure. Evolution policy now formalized: **D-015** (additive, subtype-first, human + frontier-LLM curated; on-prem extractor conforms only).
- Layer-D validation (validating LLM-extracted behavioral triples without exhaustive human review) is the key unsolved problem inherited from prior work.
