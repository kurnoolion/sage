# Project-init interview — 3gpp-kg

Captured 2026-06-05 during `project-init`. Source of truth for `--re-init`.

## Design inputs

- `docs/compact/design-inputs/3GPP_Graph_RAG_Conversation_Gemini.md` — a design
  conversation (with Gemini) exploring a Graph-RAG Q&A bot for US MNO device
  requirements built on a 3GPP-spec substrate. **Note:** the MNO Q&A bot is the
  *motivation* captured in that artifact, but it is **explicitly out of scope** for
  this project (see Topic 1). The design input is retained for the UE-ontology and
  ingestion ideas it contains (ASN.1 parsing, protocol-layer/procedure/message/IE
  entity model, SKOS/NRM/SID taxonomy references, TeleQnA eval set).

## 1. What we're building

A **3GPP taxonomy for UE-related specifications**, and then a **knowledge graph**
built on top of that taxonomy. Two sequenced deliverables:

1. Get the **UE-spec taxonomy** right first (the organizing skeleton — series /
   working group / spec / release, plus the UE-domain entity types: protocol layers,
   procedures, messages, information elements, timers, states, capabilities).
2. Build the **knowledge graph** on that taxonomy (the typed relationships between
   those entities, extracted from the specs).

The MNO device-requirements Q&A bot is **not** part of this project — it was only the
downstream motivation. Sole focus: a correct, well-structured 3GPP UE taxonomy and KG.

## 2. How we're building

Deferred — the user explicitly chose **not to jump to implementation** yet. Decisions
to make in the architecture phase:

- **Graph/taxonomy store.** Scale is *not* the differentiator: even the full UE
  Access-Stratum + NAS set across several releases (ASN.1 from TS 38.331 alone yields
  ~10⁴ IE nodes) lands around 10⁵–10⁶ nodes/edges — fits on one machine in any serious
  store. The real axis is **formal taxonomy semantics + multi-SDO interop** (RDF triple
  store + SKOS/OWL — Jena/Fuseki, GraphDB, Oxigraph) **vs. pragmatic flexibility for
  LLM-extracted triples** (property graph — Neo4j / Memgraph). Soft lean toward RDF/SKOS
  for the taxonomy layer because v1 is "get the taxonomy right" and future extension to
  GSMA/OMA/IETF rewards URI-based identity. Logged as an Open question; resolve as a
  `D-XXX` in architecture.
- **Language / tooling.** Python is the likely default (ASN.1 parsing, local-LLM
  tooling), but unconfirmed. `structure-conventions.md` seeded with a *provisional*
  Python convention — confirm or replace before the first `regen-map`.
- **Extraction approach.** Likely hybrid: deterministic ASN.1 parsing for structural
  sub-graphs + LLM-assisted semantic extraction for behavioral triples (from the design
  input). Not committed.

## 3. Stakeholder map & contribution surfaces

**TODO.** Deferred by the user. To be filled during the requirements phase. Until then,
PROJECT.md Contributors carries a single owner/dev row plus a TODO marker. The absence
of a domain-validator / ground-truth channel is itself a v1 risk to revisit (taxonomy
correctness needs a telecom-domain check).

## 4. Domain constraints

- Domain: 3GPP UE / modem protocol specifications (Access Stratum + NAS).
- **Data is public** (published 3GPP specs) — no NDA / confidentiality constraint.
- No MNO requirements, no proprietary carrier data in scope.
- **Possible future extension** to GSMA, OMA, and IETF specs — the taxonomy/KG design
  should not foreclose multi-SDO sourcing.
- Not real-time, not regulated, no strong scale driver. Correctness/completeness of the
  taxonomy and extracted relationships is the quality bar that matters.

## 5. LLM access model

The dev assistant (Claude) **has access to the actual data** — the specs are public —
**and** to the produced artifacts (taxonomy/graph files on disk). **No runtime access**
(but there is essentially no interactive "runtime" in scope; the deliverables are data
artifacts). → Treated as effectively full-access. No heavy limited-access augmentation;
a light convention of compact, pasteable parse/coverage/fingerprint reports is adopted
because it doubles as the project's eval signal.

## 6. Pain points (what the AI should catch)

- LLM **hallucinating** or mis-typing extracted triples / relationships.
- **ASN.1 parse drift** across spec releases/versions (TS 38.331 changes per release).
- **Stale data** when specs are updated (citations/nodes pointing at superseded text).
- **Taxonomy completeness/correctness** gaps — missing entity types, mis-placed nodes.
- **Eval regressions** as the pipeline changes (precision/recall of extraction drops).

## 7. Artifact preferences

- Markdown for docs/designs/requirements.
- (Notebooks/other formats not specified — assume Markdown-first.)

## Team experience with AI-assisted dev

Not stated explicitly. Inferred **mixed, leaning experienced** — the user reasons
fluently about telecom protocol structure and Graph-RAG architecture, and pushed back
to sharpen scope. EIP tone calibrated to the experienced end (direct, terse-where-safe),
without assuming COMPACT-process fluency.

## Observability posture

**Medium**, with a specific shape: runtime/perf observability is **Light** (no persistent
metrics DB, no latency/throughput infra — there's no serving runtime in scope), but
**extraction/taxonomy quality metrics are load-bearing** (parse coverage, extraction
precision/recall against a held-out / TeleQnA-style set, node/edge counts by type,
taxonomy completeness). Quality eval is the measurement that drives the work.
