# Decisions

ADR-style log. IDs are sequential and stable; entries are immutable — supersede via a new
entry with a backward link rather than rewriting. These were taken during phase-0 (research)
and promoted here on 2026-06-07; several were first captured in `docs/research/01–04`.

---

## D-001: Project scope — UE-focused 3GPP taxonomy + knowledge graph
**Status**: Active
**Date**: 2026-06-05
**Context**: The motivating use case was a Q&A bot over US-MNO device requirements built on a
3GPP substrate. That bot is broad and downstream.
**Decision**: This project builds a **taxonomy + knowledge graph of UE-related 3GPP
specifications** — and nothing else. The MNO requirements bot, override/delta mapping, and any
serving/Q&A runtime are **out of scope**. Possible future extension to GSMA / OMA / IETF specs.
**Why**: The taxonomy/KG is the hard, reusable foundation; the bot was only the motivation.
Narrow scope keeps the work tractable and correct.
**Consequences**: Deliverables are data artifacts, not an application. UE-relevance is the
standing filter for what gets modelled. Multi-SDO is designed-for but deferred.

## D-002: Two orthogonal hierarchies, joined by `DEFINED_IN`
**Status**: Active
**Date**: 2026-06-05
**Context**: 3GPP knowledge has two kinds of structure — where it's *published* vs. what it's
*about* — and forcing them into one tree is a classic ontology mistake.
**Decision**: Model a **document/provenance hierarchy** (corpus structure: org → spec → clause)
separately from the **domain/conceptual hierarchy** (UE → stratum → layer → entities), joined by
a `DEFINED_IN` provenance link from domain entities to clauses.
**Why**: They evolve independently and serve different queries; the join makes every fact
traceable to source.
**Consequences**: Every KG fact carries provenance into the corpus. See `docs/research/01`.

## D-003: Three-layer separation — corpus / ontology / knowledge graph
**Status**: Active
**Date**: 2026-06-06 (refines the initial "four-layer" framing in `docs/research/04`)
**Context**: Asked whether 100% verbatim spec text belongs in the ontology/KG.
**Decision**: Keep **three layers**: (1) **corpus document store** — complete verbatim clause
text, the *only* place 100% text lives; (2) **ontology** — the schema; (3) **knowledge graph** —
**text-free** instances with provenance refs into the corpus. The KG links into the corpus; it
never embeds bulk text (only short locator anchors).
**Why**: Structured layers are selective (for reasoning/traversal); the corpus is complete
(for retrieving exact normative text). One artifact can't serve both. Losslessness comes from
*linking* to the complete corpus, not from encoding prose as graph structure.
**Consequences**: Coverage targets differ — ~100% **text** coverage in the corpus, ~100%
**conceptual** coverage (vs. competency questions) in the ontology/KG. Chasing text coverage in
the KG is explicitly a non-goal.
**Alternatives considered**: A standalone "taxonomy" layer as a fourth peer — rejected (see D-004).

## D-004: Taxonomy is folded into the ontology; concept scheme + corpus index are adjuncts
**Status**: Active
**Date**: 2026-06-06
**Context**: "Taxonomy vs ontology" — an ontology already contains a type hierarchy.
**Decision**: (a) The **entity-type hierarchy** lives **inside the ontology** (`subtype_of`,
root `Entity`) — no separate taxonomy file. (b) The **document taxonomy** is the **corpus index**
(it pairs with the corpus, not the ontology). (c) The **domain concept scheme**
(`UE → AS/NAS → RRC/MAC/…`, SKOS-style) is a **curated adjunct**: each concept is a KG instance
typed by the ontology; KG entities attach via `IN_LAYER`; concepts nest via `BROADER`.
**Why**: A taxonomy is "an ontology with only is-a edges," so the type hierarchy belongs in the
ontology. The concept scheme is the stable **cross-spec / cross-SDO hub**.
**Consequences**: One shared ontology across specs; the concept scheme is the join point for
adding NAS/IMS/other SDOs. See `rrc-pilot/README.md`.

## D-005: Granularity principle (asymmetric) + per-edge modality & confidence
**Status**: Active
**Date**: 2026-06-05 (sharpened 2026-06-06)
**Context**: A clause's nested conditional "shall" logic could be exploded into thousands of
edges — the place LLM extraction hallucinates.
**Decision**: The KG **indexes** the specs, it does not **re-encode** them. Restraint is
**asymmetric**: fully materialize the deterministic structural tree (ASN.1 `CONTAINS`, Layer C);
be **selective** with behavioural prose (Layer D), materializing only edges that answer a
competency question. Every edge carries `modality` (asn1/prose/curated) and `confidence`.
**Why**: Abstraction is the KG's value; exact logic stays in the linked corpus. Modality/
confidence let us trust the deterministic backbone and concentrate validation on fuzzy edges.
**Consequences**: Competency questions are the test for whether an edge earns its place.
See `docs/research/02`, `03`.

## D-006: The schema is an extensible seed
**Status**: Active
**Date**: 2026-06-05
**Decision**: Entity and relationship types are an **open set**, expected to grow per spec; add a
type only when a competency question demands it; avoid premature closure.
**Why**: Each new spec reveals new structure (RRC → +`UEVariable`, `CONFIGURES`, …; IMS will add
`NetworkElement`, `SIPMethod`, `SIPHeader`, …).
**Consequences**: Ontology is versioned and shared; growth is normal, not drift.

## D-007: Store-agnostic now; production store deferred
**Status**: Open / Deferred
**Date**: 2026-06-06
**Context**: RDF triple store + SKOS/OWL vs. property graph (Neo4j) is a real architecture choice.
**Decision**: Keep all layers as **plain JSON** for the pilots; **defer** the store choice until
the schema stabilizes across RRC + IMS.
**Why**: Scale is not the deciding factor (10⁵–10⁶ nodes fits either on one machine); the real
axis is formal taxonomy/interop (RDF/SKOS) vs. pragmatic flexibility (property graph). Decide it
with evidence, not up front.
**Consequences**: The model stays store-neutral; both options remain open. Revisit after IMS.

## D-008: Build-time validation invariants (KG ⊨ ontology, KG ⊨ corpus)
**Status**: Active
**Date**: 2026-06-06
**Decision**: The build **must** validate, with zero errors, that (a) every KG entity/relationship
type is declared in the ontology and every relation's endpoints obey `domain`/`range`
(**KG ⊨ ontology**), and (b) every provenance clause resolves and every anchor locates in that
clause's text (**KG ⊨ corpus**).
**Why**: These are the correctness contract between layers — and the hallucination guardrail for
automated extraction (non-conforming triples are rejected).
**Consequences**: All extraction (manual or LLM) passes through these checks before merge.

## D-009: Corpus copyright / commit policy
**Status**: Active
**Date**: 2026-06-05 (extended 2026-06-07)
**Decision**: Downloaded specs and derived corpus stores (`corpus/raw|extracted|store`) are
**gitignored** (3GPP copyright). The ontology, concept scheme, corpus index, KG, and all tooling
are **committed**. The committed KG carries only **short provenance anchors**, never bulk prose.
Generated viewer HTML (embeds prose) is gitignored; the generator scripts are committed.
**Why**: Don't redistribute copyrighted specs; keep the reproducible, non-infringing artifacts
versioned.
**Consequences**: Anyone can rebuild the corpus from the public specs via the committed tooling.

## D-010: Extraction approach — curated gold seed + few-shot + on-prem local model
**Status**: Accepted (implementation pending)
**Date**: 2026-06-07
**Context**: A full-spec KG (e.g. all UE-relevant clauses of TS 24.229) cannot be hand-authored.
**Decision**: Build a pipeline where: I curate a small **gold seed** of example facts per doc and
a **few-shot extraction prompt** (examples + ontology + clause text → schema-valid JSON triples);
a **deterministic pass** runs first (clause graph, cross-refs, SIP vocab, tables, roles) to
provide canonical anchors; an **on-prem local model** (OpenAI-compatible endpoint) does the
behavioural prose extraction over **UE-relevant** clauses; outputs are validated (D-008),
deduplicated/entity-resolved, and low-confidence triples go to a **review queue** rather than
silently merged. The gold seed doubles as the precision/recall eval set.
**Why**: Puts correctness-critical work (schema, examples, prompt, validation) under human control
and the volume on local compute; few-shot from curated examples yields schema-conforming output;
validation + review queue contain hallucination.
**Consequences**: Per-doc gold examples + prompt; one shared ontology; a model-agnostic client.
Pipeline to be designed/built after the upcoming discussion.

## D-011: Multi-release modelling — shared identity + versioned assertions
**Status**: Active
**Date**: 2026-06-07
**Context**: We will ingest many 3GPP releases (Rel-15…19+) of each spec. A release is a
snapshot of evolving entities; we must keep history without duplicating unchanged content.
**Decision**:
- **Corpus**: per-version snapshots (already), one frozen version per release; provenance is
  `(spec, version, clause)` — already release-aware.
- **Ontology + concept scheme**: cumulative / release-agnostic (one shared schema; new
  types/concepts get an optional `introduced_in`).
- **KG**:
  1. **Release-agnostic entity identity** — ids are semantic (`type+name+layer`), never the
     clause number (clauses renumber across releases). One node per logical entity.
  2. **`Release` is a first-class entity** (ordered via `NEXT_RELEASE`).
  3. **Every entity/relation/attribute is release-stamped** with `observed_in` (releases we've
     ingested it from), `introduced_in`, `valid_until` (null = current), and `supersedes`.
     Unchanged facts are stored once with an open range — size is O(distinct facts), not
     O(facts × releases).
  4. **Time-varying attributes are sets of immutable value-assertions** (SCD-2 / bitemporal):
     a change adds a new assertion (`valid_from..valid_until` + provenance + `supersedes`); all
     prior values are retained and independently traceable. Querying a value at release N =
     the assertion whose range covers N; "current" = the open assertion.
  5. **Lifecycle is computed, not extracted** — extract each release as an independent snapshot;
     a deterministic **diff** step opens/closes assertions and builds the `supersedes` chain.
**Why**: Shared identity + versioned assertions deduplicates, makes "what changed between
releases" a first-class query, keeps the LLM reasoning about one release at a time, and
preserves full history with per-release provenance.
**Consequences**: Release fields are baked into the schema from day one (stamped `Rel-19` now;
`introduced_in` backfilled by the diff as earlier releases land). Feeds **D-007**: versioned
facts are edge-properties in a property graph vs. reification / named-graphs-per-release in RDF.
**Alternatives considered**: Separate KG per release — rejected (massive duplication; no
first-class change tracking; cross-release questions need graph diffs).

## D-012: Change-tracking / derivation model
**Status**: Active (model decided; pipeline implementation pending)
**Date**: 2026-06-07
**Context**: Ingesting many releases (and later MNO overlays) needs history without duplication or
churn. Full design in `docs/design/scratchpad.md` §15.
**Decision**: (a) **Deterministic semantic keys** for entities/relations/attributes + content-derived
assertion ids. (b) **Snapshots are the source of truth; the unified KG is a pure, recomputed
projection** (`derive()`), so ingestion is **order-independent** and re-ingest is idempotent.
(c) `introduced_in`/`removed_in` from presence diff; `supersedes` from value changes (SCD-2
value-assertions coalesced into segments). (d) **Review queue** for renames/merges/splits/conflicts
(durable alias/decision file feeds the next derive). (e) Lifecycle is **observed-set-relative**:
`introduced_in` is a lower bound (`introduced_at_floor`); non-contiguous releases give bracketed
boundaries.
**Why**: Order-independent, churn-free, full-history, human-controlled where machines are unsafe.
**Consequences**: Re-key from slugs to namespaced ids done; pipeline = snapshot extractor + derive +
review queue. Underpins D-013 (MNO overlays use the same machinery on a 2nd axis).

## D-013: NORA integration contract
**Status**: Active (contract drafted; projection API + representative-version table pending)
**Date**: 2026-06-07
**Context**: NORA (`~/work/nora`) is the downstream MNO-requirements analyzer; this project is its
3GPP substrate. NORA already has: a unified graph partitioned by `mno`+`release`; `Standard_Section`
(`std:spec:release_num:section`) + `Feature` + `maps_to`; **delta edges `defers_to`/`constrains`/
`overrides`/`extends`**; `version_of` cross-release diffing; generic 3GPP ingestion
(`reference_index.json` + `spec_parsed.json`); a query pipeline that pulls Standard_Section text into
synthesis. Full read + design in scratchpad §H.
**Decision**:
- **Boundary**: anchor + augment; **ownership A** — this project owns the entire 3GPP vertical and is
  a standalone general 3GPP KB; NORA's `standards/`+`taxonomy/` become consumers/adapters; proprietary
  MNO features stay in NORA. **One-way; no MNO data in this repo.**
- **Interface NORA → us = a plain `(spec, release)` manifest** (derived from NORA's
  `reference_index.json`). No MNO data crosses.
- **Ids**: namespaced deterministic (`3gpp:…`). **Section/release joins are deterministic transforms**
  (`std:24.229:17:5.1.1.2` ↔ `3gpp:24.229/Rel-17/clause/5.1.1.2`; `release_num`↔`Rel-N` + a
  `(spec,release)→representative-version` table; `24.301`↔`TS 24.301`). **Feature↔concept is a curated
  crosswalk, Option Y** (3GPP-grounded features adopt our concept/entity ids; proprietary keep
  `feature:LOCAL_*` — the namespace encodes anchored-vs-proprietary). **Base assertions carry stable
  ids** because MNO overrides target a specific assertion, not just an entity.
- **Requirement-as-delta classification maps onto NORA's existing edges** (no new vocabulary):
  RESTATE→`defers_to`; CHANGE→`overrides`(differ)/`constrains`(narrow, incl. conditional "follow
  §x.y.z when foo"); CREATE→`extends`(add)/pure-new(`maps_to` only). Classify **per atomic claim**.
  MNO assertions use the same versioned-assertion machinery (D-012) on a 2nd `(MNO, MNO-release)` axis,
  carrying the targeted 3GPP-release baseline.
- **Per-release projection**: we expose a per-release view (looks like NORA's `Standard_Section` set)
  plus change-queries; our entity layer reconciles NORA's per-release section duplication.
- **Enrichment/query**: NORA pulls our verbatim corpus prose (via resolved clause id) + structured
  base assertions into requirement enrichment and synthesis (upgrades NORA's existing Standard_Section
  text inclusion to entity-level deltas + precise provenance).
- **Shared concern**: generic document extraction → eventual shared lib; download + section-parse owned
  here.
**Why**: NORA already converged on this architecture; the contract reuses its vocabulary. Our value =
entity layer + concept scheme + change-tracking + verbatim provenance above NORA's section trees + flat
features.
**Consequences**: NORA re-keys grounded features to our ids; needs the rep-version table; classification
fidelity is **bounded by our base-KG coverage** (structured vs prose fallback); a **post-ingestion risk
auditor** is required (scratchpad §I). Pending: per-release projection API spec; where MNO assertions
physically live (NORA-side overlay referencing our ids).

## D-014: Project named SAGE
**Status**: Active
**Date**: 2026-06-08
**Context**: The project (previously the placeholder `3gpp-kg`) needed a real name, consistent
with sibling projects that use a pronounceable backronym: NORA (Network Operator Requirements
Analyst), HILDA (Human In the Loop Deliverable Automation), APEX (Ai Powered EXcellence).
**Decision**: Name it **SAGE = Specification-Anchored Graph of Entities**. Repo and directory
renamed `3gpp-kg` → `sage`; GitHub repo `kurnoolion/3gpp-kg` → `kurnoolion/sage`; docs rebranded.
"3GPP" still refers to the standards body (e.g. the `3gpp:` id prefix, "3GPP specs/vertical"),
which is unchanged — only the *project name* moved off `3gpp-kg`.
**Why**: Matches the sibling-project naming convention; the backronym maps to the design (graph
of entities, spec-anchored provenance); the "sage = knowledge" connotation fits a knowledge base.
Alternatives weighed: ATLAS (substrate metaphor), GRETA (women's-name lineage).
**Consequences**: Refer to the project as SAGE; NORA's downstream contract (D-013) calls its
substrate SAGE. The old GitHub name auto-redirects; a temporary `~/work/3gpp-kg` compat symlink
may exist until sessions move to `~/work/sage`.

<!--
Template for new entries:

## D-0NN: Short descriptive title
**Status**: Active
**Date**: YYYY-MM-DD
**Context**: What problem prompted this decision?
**Decision**: What was chosen?
**Why**: Reasoning; alternatives considered in passing.
**Consequences**: What does this force or rule out?
**Alternatives considered** *(optional)*:  - Option X — rejected because ...
**Supersedes** / **Superseded by** *(optional)*:  - [D-XXX](#d-xxx)
-->
