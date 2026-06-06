# Phase-0 Pilot 1 — RRC Connection Establishment (TS 38.331)

**Status**: Phase-0 pilot, iteration 1. Grounded in real spec text.
**Source**: TS 38.331 **v19.2.0** (Rel-19, file `38331-j20`), clauses **5.3.3** (procedure
prose, Layer D) and **6.2.2** (message ASN.1, Layer C). Extracted slices live under
`corpus/extracted/38331-j20/slices/` (corpus is gitignored — 3GPP copyright).
**Goal**: prove the two-hierarchy + entity/relationship model on one real procedure, end-to-end,
on the *easy* (ASN.1-anchored) layer first.

---

## 1. Competency questions this slice must answer

These anchor *what's worth modeling* (and what isn't):

1. What messages are exchanged in RRC connection establishment, in what direction?
2. Which timer supervises the procedure, and what happens on its expiry?
3. What UE state holds before the procedure, and what state does it end in?
4. What IEs does each message carry? Which are optional?
5. Which other (sub-)procedures does it invoke?
6. Which *other* procedures reuse the same messages (e.g. `RRCSetup`)?
7. What triggers the procedure, and what are its preconditions?
8. Where (spec/release/clause) is each of these defined?

## 2. Worked instance model (grounded in the actual text)

**Entities** (instance — type), with the clause they're drawn from:

| Instance | Type | Provenance | Modality |
|---|---|---|---|
| RRC connection establishment | Procedure | 5.3.3 | prose |
| RRCSetupRequest, RRCSetup, RRCSetupComplete, RRCReject | Message | 6.2.2 / 5.3.3 | asn1 + prose |
| ue-Identity, establishmentCause, radioBearerConfig, masterCellGroup, selectedPLMN-Identity, dedicatedNAS-Message, ng-5G-S-TMSI-Value, registeredAMF, guami-Type, s-NSSAI-List | InformationElement | 6.2.2 (`*-IEs`) | asn1 |
| T300 | Timer (supervises) | 5.3.3.2 / 5.3.3.7 | prose |
| T301, T319, T380, T390, T302, T320, T331 | Timer (stopped) | 5.3.3.4 | prose |
| RRC_IDLE, RRC_CONNECTED, RRC_INACTIVE | State | 5.3.3.2 / 5.3.3.4 | prose |
| SRB0, SRB1 | **Bearer** *(new type — see §5)* | 5.3.3.1 / 5.3.3.2 | prose |
| "T300 expiry" | Event | 5.3.3.7 | prose |
| establishment of RRC connection (upper-layer request) | Trigger/Event | 5.3.3.2 | prose |
| RRC | ProtocolLayer | (skeleton) | curated |

**Relationships** (typed edges), each grounded in a specific sentence:

| Edge | Grounding (paraphrased from text) | Modality / confidence |
|---|---|---|
| Procedure —TRIGGERED_BY→ (upper-layer request) | "UE initiates the procedure when upper layers request establishment…" | prose / med |
| Procedure —HAS_PRECONDITION→ State:RRC_IDLE | "…while the UE is in RRC_IDLE and it has acquired essential system information" | prose / med |
| Procedure —EXCHANGES→ Message (dir: UE→NW \| NW→UE) | RRCSetupRequest↑, RRCSetup↓, RRCSetupComplete↑ | prose / high |
| Procedure —ALTERNATIVE_OUTCOME→ RRCReject | "RRC connection establishment, network reject" (Fig 5.3.3.1-2) | prose / med |
| Procedure —STARTS→ Timer:T300 | "start timer T300" | prose / high |
| Procedure —STOPS→ Timer:{T300,T301,T319,T390,T302,…} | "stop timer T300, T301, T319 …" | prose / high |
| Procedure —TRANSITIONS_TO→ State:RRC_CONNECTED | "enter RRC_CONNECTED" | prose / high |
| Procedure —ESTABLISHES→ Bearer:SRB1 | "RRC connection establishment involves SRB1 establishment" | prose / high |
| Procedure —INVOKES→ Procedure:{cell group config (5.3.5.5), radio bearer config (5.3.5.6), unified access control (5.3.14)} | "perform the … procedure in accordance with … as specified in 5.3.5.5" | prose / high |
| Event:"T300 expiry" —ON_EXPIRY_OF→ Timer:T300 | clause 5.3.3.7 | prose / high |
| Message —CONTAINS→ IE (attr: optional?) | from ASN.1 `*-IEs` SEQUENCEs; `OPTIONAL` keyword → optional=true | **asn1 / high (deterministic)** |
| IE:establishmentCause —HAS_DOMAIN→ EstablishmentCause (enum) | ASN.1 type reference | asn1 / high |
| Message:RRCSetup —REUSED_BY→ Procedure:{re-establishment 5.3.7.8, resume 5.3.13.7} | "Reception of the RRCSetup by the UE" appears under 5.3.7/5.3.13 | prose / high |
| <every node/edge> —DEFINED_IN→ Clause (Hierarchy A join) | python-docx heading index | deterministic / high |

## 3. The key finding — granularity (anti-over-engineering)

The procedure prose is **deeply nested conditional "shall" logic** (bullet levels 1>/2>/3>/4>/5>
= if/else trees; 5.3.3.4 alone is ~150 such steps). **We do NOT materialize each action as graph
structure.** That path explodes the graph and is exactly where LLM extraction hallucinates.

**Principle:** the graph captures **salient typed entities and the relationships that answer a
competency question**; the *exact normative procedural logic stays in the linked prose*, reached
via `DEFINED_IN` provenance. The KG is an **index and a relationship map over the specs, not a
re-encoding of the specs.** Competency questions (§1) are the test for whether an edge earns its
place.

## 4. What worked

- The **two-hierarchy + `DEFINED_IN` join (D1)** held cleanly — every entity resolved to a clause.
- The **Layer C / Layer D split (D-research)** is real and *operationally useful*: `CONTAINS`
  (Message→IE) edges came **deterministically** from ASN.1 at high confidence; behavioral edges
  came from prose at medium confidence. → **Edges should carry `modality` + `confidence`
  attributes.** This lets us trust/serve the deterministic backbone and concentrate validation on
  the fuzzy behavioral layer — a concrete, valuable design output.
- The upper skeleton (UE → Stratum → Layer → entity types) was sufficient to type every instance.

## 5. Findings that feed back into D2/D3

- **Add `Bearer` (SRB/DRB/MRB) as a first-class entity type.** SRB1 establishment *is the
  purpose* of the procedure; bearers are touched constantly. (D2 had this as an open question —
  the pilot answers **yes, first-class.**)
- **`Event` confirmed first-class** (T300 expiry, upper-layer request). Triggers are Events.
- **Messages are shared across procedures** (`RRCSetup` is used by establishment, re-establishment,
  resume). → The graph must store one Message node and use `EXCHANGES`/`REUSED_BY` edges with a
  *role/context* attribute; **never duplicate a message per procedure.**
- **`INVOKES` (Procedure→Procedure) is essential** — procedures compose (setup invokes
  cell-group-config + radio-bearer-config). The graph needs sub-procedure composition.
- **Cross-spec references are real edges** (TS 38.321 MAC, TS 23.501, TS 24.501, TS 38.351). The
  UE filter (D3) must keep these as `REFERENCES` edges even when the target spec is out of v1 scope
  (dangling-but-typed references), so we don't lose the cross-layer/cross-spec structure.

## 6. Candidate schema (TBox) emerging from the pilot

**Entity types:** ProtocolLayer, Procedure, Message, InformationElement, Timer, State, Event,
Condition, Capability, **Bearer**. *(Channel, Identity still open — defer to a later slice.)*

**Relationship types:** DEFINED_IN, CONTAINS, HAS_DOMAIN, EXCHANGES, REUSED_BY, STARTS, STOPS,
TRANSITIONS_TO, HAS_PRECONDITION, TRIGGERED_BY, ALTERNATIVE_OUTCOME, ESTABLISHES, INVOKES,
ON_EXPIRY_OF, REFERENCES.

**Edge attributes:** `modality` (asn1|prose|curated), `confidence` (high|med|low), plus
relation-specific attrs (e.g. `direction` on EXCHANGES, `optional` on CONTAINS, `role` on REUSED_BY).

> **This is a seed, not a closed set (agreed 2026-06-05).** Entity and relationship types are
> expected to *grow* as we model more specs. The schema is open/extensible by design — each new
> slice may introduce new types; we add them when a competency question demands it, and avoid
> premature closure of the type system.

## 7. Next steps

- React/refine the §6 candidate schema with the user → this becomes the seed TBox.
- Extend the pilot to **RRC reconfiguration (5.3.5)** to test the schema on a configuration-heavy
  (not connection-setup) procedure before declaring the method validated.
- Then **Pilot 2 (IMS)** — stress the prose-only (no ASN.1) case.
- Productize the slice extractor (currently ad-hoc python-docx) into a committable tool once the
  schema stabilizes.
