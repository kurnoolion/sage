# Project: 3gpp-kg

*Identity: who / why / scope boundaries. Behavioral specs (FR / NFR) live in `requirements.md`.*
*Draft seeded at project-init from `design-inputs/` + interview — refine during the requirements phase.*

**One-line**: A 3GPP taxonomy for UE-related specifications, and a knowledge graph built on it.

**Problem**: 3GPP UE-side specifications (Access Stratum + NAS) are dense, heavily
state-dependent, and spread across many specs, working groups, and releases. There is no
single ready-made, semantically complete taxonomy/ontology of the UE domain to build on.
Downstream work (e.g. reasoning about device behavior, or enriching carrier requirements
that use 3GPP as a substrate) needs a correct, well-structured representation of the
standards first. This project builds that foundation: get the **UE-spec taxonomy** right,
then construct a **knowledge graph** of the entities and relationships on top of it.

**Users**: The taxonomy/KG is the product. Direct consumers are knowledge-engineering and
telecom-protocol work that needs structured access to UE-spec entities (protocol layers,
procedures, messages, information elements, timers, states, capabilities) and their
relationships. *(Detailed stakeholder map — TODO, see Open questions.)*

**In scope for v1**:
- A taxonomy of UE-related 3GPP specifications and their UE-domain entity types.
- A knowledge graph of typed relationships among those entities, sequenced after the taxonomy.
- Provenance from each node/relationship back to its source spec section.

**Out of scope (explicit non-goals)**:
- The MNO device-requirements Q&A bot (the downstream motivation, not this project).
- MNO / carrier requirements, override / delta mapping, certification/compliance logic.
- Non-UE 3GPP domains (Core Network billing, OSS/BSS, transport interfaces).
- A serving runtime / interactive query product (this project produces data artifacts).

**Success criteria**: A taxonomy that correctly and measurably covers the targeted UE specs,
and a knowledge graph on it whose extracted relationships meet an agreed quality bar
(coverage + precision/recall against a held-out / TeleQnA-style check). *(Make measurable in
`requirements.md` NFRs.)*

**Open questions** *(maintained during Requirements phase; removed when resolved or deferred)*:
- **Spec coverage**: which exact series/specs and releases define v1 (e.g. TS 38.331 RRC,
  38.321 MAC, 38.322 RLC, 38.323 PDCP, 24.501 NAS; which releases)?
- **Store choice**: RDF triple store + SKOS/OWL vs. property graph (Neo4j). Architecture-phase
  `D-XXX`; scale is not the deciding factor.
- **Language / tooling**: Python assumed (ASN.1 parsing, LLM tooling) but unconfirmed.
- **Taxonomy correctness — who validates?** No domain-validator / ground-truth channel is yet
  named. Unowned validation is a v1 risk.
- **Extraction approach**: deterministic ASN.1 parsing + LLM semantic extraction — extent of each?

**Contributors**:

| Stakeholder / Role | Contributes | Interface | Feedback loop |
|---|---|---|---|
| Owner / dev | Taxonomy + KG design, code, decisions | Direct file/git edits | Normal flow; decisions logged at `/close-session` |
| *Domain validator* — **TODO** | Taxonomy correctness checks, ground-truth labels | TBD | TBD |
| *Eval data* — **TODO** | Held-out / TeleQnA-style evaluation set | TBD | TBD |

*Stakeholder map deferred at project-init. The missing domain-validator and eval-data rows are
v1 risks (taxonomy correctness needs a telecom-domain check) — resolve during requirements or
carry as `STATUS.md` Flags.*
