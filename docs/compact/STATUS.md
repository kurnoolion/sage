# Status

**Active phase**: requirements
**Last updated**: 2026-07-17

> **Note**: Formally still pre-requirements; work has moved into implementation. The three-layer
> architecture is built + validated on the **RRC pilot** (TS 38.331, clauses 5.3.3 + 5.3.5 — a
> deliberately small schema/method validation, not complete). For **IMS** (TS 24.229) the **D-010
> extraction pipeline now runs**: deterministic spine + on-prem LLM stage, producing per-version
> snapshots (corpus stays gitignored — rebuild via `corpus/fetch_spec.py`). Decisions D-001…D-021
> recorded. Research artifacts live in `docs/research/` (outside the COMPACT state files).

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
- 2026-06-08 D-010 pipeline **deterministic spine** built (`pipeline/`): UE filter → extractors → merge → validate → snapshot; TS 24.229 169 UE clauses → 149 entities / 30 relations, 0/0. Viewer wired to pipeline snapshots; ambiguous procedure anchors demoted to the review queue.
- 2026-06-08 Recorded **D-015** (ontology evolution: additive, subtype-first, human + frontier-LLM curated) and **D-016** (post-ingestion risk-monitoring auditor — design promoted from scratchpad §I).
- 2026-06-09 On-prem enablement: repo-root-anchored paths; `corpus/fetch_spec.py` rebuilds the gitignored corpus from the public HF dataset (reuses NORA's downloader) — **D-021**; `SpecConfig` made version-agnostic (any fetched version runs).
- 2026-06-09 LLM stage hardened for local models: structured logging + stable error codes (**D-017**), `llm_debug --clause` prompt/response inspection, deterministic paragraph-boundary chunking with hard-split fallback (**D-018**), cumulative progress line + mid-run checkpoint snapshots, configurable timeout.
- 2026-06-09 Whitespace-normalized anchor matching (**D-019**) — removes false KG⊨corpus warnings.
- 2026-06-09 Parallel multi-LLM runs via `--label` + per-run LLM overrides; `pipeline/compare.py` diffs runs by fact id (**D-020**). README documents the full operate/debug/compare workflow.
- 2026-07-16 Deep-research validation of all documented external claims (25 verified, 0 refuted): headline findings stand; research doc 01 refreshed (§1.4) — TelcoAgent + DeepSpecs added to the landscape, Telco-oRAG wording softened, TSpec-LLM gating noted, spec-sourcing question closed (GSMA/3GPP mirror). Rel-19 confirmed frozen; TS 24.229 now at 19.7.0 + first Rel-20 20.0.0 (`k` prefix) — fresh diff candidates for D-012.
- 2026-07-16 Full-text deep-read of TelcoAgent + DeepSpecs (research doc 01 §1.5). Verdict: TelcoAgent's pipeline is unusable as-is for SAGE but yields an **aligner stage** lead (propose-only per D-015). DeepSpecs' **CR-rationale mining** (ChangeDB/TDocDB) adopted as a D-012 idea (*what* changed + *why*); its QA sets are email-request-only. *(Two paper-level claims corrected same day by the code review below.)*
- 2026-07-16 **TelcoAgent code review** (cloned the MIT repo; research doc 05): the code is KARMA-based and richer than the paper — clause-level provenance exists, but no span grounding, evaluator never sees source text, and the prompt-mandated schema eroded (~20 free-form predicates, 71% catch-all nodes) because the builder absorbs violations — direct empirical support for D-008 hard validation. Released KG has **zero TS 38.331 edges** → RRC-pilot comparison idea dead. Adopting: (1) conflict grouping → review queue, (2) embedding-first alias suggester (doubles as D-012 alias table), (3) entity-pass-then-relation-pass prompt instruction, (4) bounded retry on unparseable output. Rejected: LLM summarization, LLM self-scored gates, LLM relevance filter, ReAct tool-loops on-prem (pending `llm_debug` evidence).
- 2026-07-16 **KARMA paper review** (doc 05 §5): TelcoAgent's upstream framework (NeurIPS'25 spotlight, biomedical, no code release). Three consequences: (1) LLM-vs-human correctness gap quantified (83.1% vs 0.625) → cited under the Layer-D flag; (2) KARMA's CRA queues conflicts for expert review — our review-queue adoption is more faithful to KARMA than TelcoAgent's auto-drop; CRA is their biggest ablation lever (~9.7%), reinforcing conflict grouping at #1; (3) adopted KARMA's ρ distance cutoff into the alias-suggester design (beyond ρ → propose new entity, not a merge). Grounding gap confirmed inherited: KARMA also extracts from paraphrased text with no provenance.
- 2026-07-17 **Reasoning-model output stripping** (NORA-aligned; commit `8b55247`). Ported NORA's `core/src/llm/openai_provider._strip_reasoning` into `pipeline/llm.py` so a reasoning model's chain of thought no longer corrupts `_parse` (its bracket-laden prose — clause refs like `[T300]`, lists — would otherwise be mistaken for the JSON array). Two paths: (a) tagged `<think>`/`<thinking>`/`<reason>`/`<reasoning>` blocks stripped **always** (multi-tag backref regex, tolerant of attributes/case, plus a dangling-close cut for servers that drop the opening tag); (b) the `===FINAL_ANSWER===` **sentinel** for *untagged* reasoning, opt-in via `SAGE_LLM_REASONING_SENTINEL` — `build_messages` appends the marker instruction to the system prompt only when enabled, keeping prompt + strip in lockstep. Live env check (not import-time) so per-run/test toggling works. 10 new tests (`TestReasoningStrip`); suite 30/30. *(Strand `telcoagent-adoption`: hardens the A4 LLM-parse path for reasoning endpoints; decision draft pending at close-session.)*
- 2026-07-17 **Truncated-reply handling** (commits `16774ee`, `e7f912f`), surfaced by a real work-PC `llm_debug` run where a reasoning model's reply was cut off mid-array (the sentinel worked; the JSON was just truncated) and `_parse` dropped every fact because the only `]` left sat inside an anchor (`RFC 3329 [48]`). Three parts: (1) `_parse` now **salvages** the complete leading objects of a truncated/unparseable array (`_salvage_array`, element-at-a-time `raw_decode`) instead of losing the chunk — also recovers a valid array trailed by prose; (2) `SAGE_LLM_MAX_TOKENS` sets the completion cap (unset → server default), sent in the request body, with `_call` warning on `finish_reason=length`; (3) **`--max-tokens`** flag on `pipeline.run` + `pipeline.llm_debug` (`endpoint()` precedence: explicit arg > env > server default), matching the `--llm-*` override pattern. Reasoning models make truncation likelier (thinking burns output budget before the JSON). 9 new tests; suite 40/40. *(Same A4 LLM-parse hardening; folds into the same close-session decision draft.)*

## In progress

- **D-013 NORA integration contract** — drafted; **9 open contract TODOs** remain (scratchpad §H.15: inbound manifest, outbound artifacts, per-release projection API, representative-version table, feature crosswalk, base-assertion id, overlay form, tier-2 edges, update cadence).
- Seed schema: **15 entity types / 24 relationship types** (release + concept-scheme aware) in `rrc-pilot/ontology/ontology.json`; agreed **extensible**. Open question: procedure modes vs. variants (research doc 03 §4).
- Running real on-prem LLM extraction over TS 24.229 and comparing two local models (D-020 labels + `pipeline.compare`). Chunked-extraction quality (D-018) not yet empirically verified.

## Next

- Evaluate the two-model comparison (LLM-fact Jaccard, review queue) and verify chunked-extraction quality on a long clause (e.g. `llm_debug --clause 5.4.3.2`).
- Ingest TS 24.229 **19.7.0** and **20.0.0** (published 2026-06-29) — first real cross-release diff for D-012 `derive()` and first `k`-prefix (Rel-20) exercise; NORA's downloader already supports it.
- Close the **D-013 contract items** (§H.15).
- ~~Diff TelcoAgent's released TS 38.331 KG against our RRC pilot KG~~ (dead 2026-07-16: their released KG has zero TS 38.331 edges — doc 05 §0). Replaced by the doc 05 §3 adoption list: **(1) conflict grouping → review queue** (small, unblocks sharper D-020 compare), **(2) embedding-first alias suggester** (propose-only; doubles as D-012 alias table), **(3) entity-first prompt instruction** (A/B via `pipeline.compare`).
- When D-012 `derive()` gets built: fold in **CR-rationale mining** (DeepSpecs-style ChangeDB/TDocDB — *what* changed + *why*) over the 24.229 19.6.0→19.7.0→20.0.0 diffs.
- Build the **post-ingestion risk auditor** (**D-016**; scratchpad §I, R1–R14).
- Formalize: `/switch-phase architecture` (or development) — active phase has lagged actual work for several sessions; when schema stabilizes across RRC+IMS, pick the production store (RDF/SKOS vs property graph).

## Flags

- Stakeholder map deferred — no domain-validator or eval-data channel named yet (v1 risk).
  *Partial lead (2026-07-16): DeepSpecs (arXiv 2511.01305) has a 350-question
  evolution-focused 5G QA set — candidate eval for the D-011/D-012 change-tracking queries.
  Deep-read caveat: **not publicly released** (code/data "upon email request") — pursuing it
  means emailing the authors.*
- Store choice (RDF/SKOS vs. property graph) unresolved — architecture-phase `D-XXX`; model so far is store-agnostic.
- Schema (entity/relationship types) is an **open/extensible seed** — expected to grow per spec; avoid premature closure. Evolution policy now formalized: **D-015** (additive, subtype-first, human + frontier-LLM curated; on-prem extractor conforms only).
- Layer-D validation (validating LLM-extracted behavioral triples without exhaustive human review) is the key unsolved problem inherited from prior work.
  *Now quantified (2026-07-16): KARMA (NeurIPS'25) reports 83.1% LLM-judged correctness vs 0.625 human-expert scores on the same triples — a ~21-point overstatement by LLM judges (doc 05 §5.1). LLM self-scoring is not a substitute for grounded/expert validation.*
