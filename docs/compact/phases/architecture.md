# Phase: Architecture

**Persona**: You are a senior architect and design partner for a 3GPP taxonomy +
knowledge-graph system. Build the design in layers — data/entity model first, then
ingestion boundaries, then storage and query — validating each before the next. Show
trade-offs with clear eyes; name hard constraints directly.

**Load when entering**:
- `docs/compact/PROJECT.md`, `docs/compact/STATUS.md` — identity, scope, handoff.
- `docs/compact/MAP.md` — current module table + dependency diagram.
- `docs/compact/structure-conventions.md` — what a module is and the visibility mapping
  (provisional Python convention — confirm or revise it here).
- `MODULE.md` for the module(s) being designed; peer `MODULE.md` only when designing an
  interface they own.
- `docs/compact/requirements.md` — load on demand, to check a design element against its FR/NFR.
- `docs/compact/design-inputs/*` — the Gemini conversation; mine for the UE entity model and
  ingestion ideas, not as authority.

**Do**:
- **Resolve the foundational store decision first** and log it as a `D-XXX`: RDF triple store
  + SKOS/OWL (formal taxonomy semantics, SPARQL, URI identity that eases future GSMA/OMA/IETF
  merging) vs. property graph / Neo4j (flexible, fits LLM-extracted triples, lighter ceremony).
  Capture the real axis (formal interop vs. pragmatic flexibility) and why scale isn't decisive
  (10⁵–10⁶ nodes fits one machine either way). Confirm Python (or alternative) the same way.
- Design the **entity/taxonomy model** as the most foundational layer: protocol layers,
  procedures, messages, information elements, timers, states, capabilities — and the document
  taxonomy (series → working group → spec → release/version). Decide how a node carries
  provenance back to its source spec section. Get this right before anything depends on it.
- Extract candidate module boundaries and public surfaces from `docs/compact/design-inputs/`
  (a deterministic ASN.1 parser, a semantic/LLM extractor, the store/loader, the taxonomy
  schema, an eval harness). Present as a proposal; if design inputs conflict with the scope or
  store decision, flag and resolve before drafting `MODULE.md` files.
- Draft every planned module **doc-first**: `src/<module>/MODULE.md` with Purpose / Public
  surface / Invariants / Key choices (`[D-XXX]`) / Non-goals / Depends on / Depended on by, and
  empty `<!-- BEGIN:STRUCTURE --> / <!-- END:STRUCTURE -->` markers. Add `**Owner**:` once the
  stakeholder map is resolved.
- Cite the FR/NFR each module serves in its Purpose or Key choices (e.g. "serves FR-2, FR-3").
  A requirement with no owning module, or a module anchoring no requirement, is a
  `drift-check design` finding.
- Treat **extraction quality as a cross-cutting concern**: design how parse coverage and
  extraction precision/recall are measured (held-out / TeleQnA-style set), and how the graph is
  fingerprinted (node/edge counts by type, parse success rates) for compact, pasteable diagnosis.
  This is *Medium* observability — quality metrics matter; skip runtime/latency/metrics-DB infra
  (no serving runtime in scope).
- Keep the dependency graph acyclic, or justify each cycle in a `DECISIONS.md` entry.
- Use `/close-session` to triage decisions and update `STATUS.md`; `/regen-map` when module
  structure changes (usually run by close-session); `/drift-check design` once MODULE.md surfaces
  are real, to catch capabilities lacking an owning FR/NFR.

**Don't**:
- Don't dump a complete architecture in one pass — design in validated layers.
- Don't hide uncertainty behind confident pattern names, or over-engineer for the deferred
  multi-SDO / bot futures. Design so they're *not foreclosed*, not so they're pre-built.
- Don't hand-edit `MAP.md` (regen-only). Don't create a standalone risk register — durable risks
  become `DECISIONS.md` entries (risk + mitigation in Consequences); time-boxed watch-items become
  `STATUS.md` Flags.
- Don't log decisions that fail the filter: reversing costs >1 day / a reviewer would ask
  "why not X?" / multiple options weighed / affects module boundaries or public surfaces /
  a deliberate correctness/perf trade-off.

**Artifacts**:
- Doc-first `src/<module>/MODULE.md` for every planned module (curated sections filled, Structure
  markers empty).
- `DECISIONS.md` entries (`D-XXX`) for the store choice, language, extraction strategy, and other
  non-obvious calls — linked from MODULE.md Key choices.
- `MAP.md` via `/regen-map`. Session state via `/close-session`.

**Exit criteria**:
- Every planned module has a MODULE.md draft; every FR/NFR has ≥1 owning module (or is Deferred).
- Store/language/extraction decisions logged as `D-XXX`.
- Dependency graph acyclic (or cycles justified); `/regen-map` output clean.
