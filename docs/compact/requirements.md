# Requirements

Last updated: 2026-06-05. Behavioral specs only — project identity and scope live in `PROJECT.md`.

<!--
How to use this file:

- Each requirement has a stable ID. IDs are never reused and never renumbered.
  - New functional requirement → next `FR-N`.
  - New non-functional requirement → next `NFR-N`.
- One sentence per requirement. Active voice. Testable where possible.
- Removed requirements are struck through in place:
    ~~**FR-3** — <original text>~~ (removed YYYY-MM-DD: <reason>)
- Items agreed to postpone go under `## Deferred` — they are not drift.
- `drift-check` reads this file. Keep it current; it is the authority for what the
  system is supposed to do, which design and implementation are checked against.

The commented candidates below were extracted from docs/compact/design-inputs/ at
project-init. They are PROPOSALS, not authoritative — confirm/edit/reject each during
the requirements phase, then promote it to a real FR-N / NFR-N entry. Do not treat a
commented line as a settled requirement.
-->

## Functional

<!--
Candidate FRs (proposals from design-inputs — confirm before promoting):
- The system ingests a defined set of UE-related 3GPP specifications.
- The system represents the UE document taxonomy: series → working group → spec → release/version.
- The system represents UE-domain entity types as taxonomy nodes: protocol layer, procedure,
  message, information element, timer, state, capability.
- The system deterministically parses ASN.1 blocks from UE specs (e.g. TS 38.331) into a
  structural sub-graph of messages and information elements.
- The system extracts behavioral relationships from spec prose (e.g. timer-expiry → state
  transition) as typed graph edges.
- Every node and relationship carries provenance to its source spec section.
- The system builds a queryable knowledge graph over the taxonomy (sequenced after the taxonomy).
-->

- **FR-1** — <behavior>

## Non-functional

<!--
Candidate NFRs (proposals from design-inputs — confirm before promoting):
- Taxonomy coverage of the targeted v1 specs meets an agreed completeness threshold.
- Extraction quality (precision/recall of relationships) meets an agreed bar against a
  held-out / TeleQnA-style evaluation set.
- ASN.1 parse success rate across targeted specs/releases meets an agreed threshold.
- The pipeline re-ingests updated spec versions without corrupting existing provenance
  (parse drift across releases is detectable).
- The chosen store handles the v1 graph (~10^5–10^6 nodes/edges) on a single machine.
-->

- **NFR-1** — <constraint + measurable criterion if applicable>

## Deferred

<!--
Entry format:
- **FR-N** — <requirement> (deferred: <why> — revisit: <trigger or date>)

Candidates (from scope decisions at project-init):
- Multi-SDO extension to GSMA / OMA / IETF specs (deferred: v1 is 3GPP UE only — revisit: after
  the 3GPP UE taxonomy + KG are validated).
- MNO device-requirements ingestion and override/delta mapping (deferred: out of project scope —
  revisit: only if this project's charter changes).
- A Q&A bot / serving runtime over the graph (deferred: out of project scope — this project
  produces data artifacts).
-->

<!-- (promote candidates above into real entries during the requirements phase) -->
