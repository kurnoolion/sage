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

## In progress

- Phase-0 schema validation — started 2026-06-05. Seed schema: 11 entity types, ~21 relationship types; agreed **extensible**. One open question: procedure modes vs. variants (research doc 03 §4).

## Next

- Pilot 2: **IMS** (TS 24.229) — prose-only stress test (no ASN.1 anchor); tests the behavioral-edge discipline without a deterministic backbone.
- Then promote D1–D4 + the seed schema into `DECISIONS.md` and populate `PROJECT.md` / `requirements.md` (formal `/switch-phase requirements`).

## Flags

- Stakeholder map deferred — no domain-validator or eval-data channel named yet (v1 risk).
- Store choice (RDF/SKOS vs. property graph) unresolved — architecture-phase `D-XXX`; model so far is store-agnostic.
- Schema (entity/relationship types) is an **open/extensible seed** — expected to grow per spec; avoid premature closure.
- Layer-D validation (validating LLM-extracted behavioral triples without exhaustive human review) is the key unsolved problem inherited from prior work.
