# Phase-0 Pilot 1b — RRC Reconfiguration (TS 38.331 §5.3.5)

**Status**: Phase-0 pilot, iteration 2. Grounded in real spec text.
**Source**: TS 38.331 **v19.2.0**, clauses **5.3.5** (prose, Layer D — 2318 paragraphs) and
**6.2.2** ASN.1 (`RRCReconfiguration`, `RRCReconfigurationComplete`, `ReconfigurationWithSync`).
**Goal**: stress the seed schema from Pilot 1 on a **configuration-shaped** procedure (not an
exchange-shaped one) and record what new types/relationships it forces.

This doc records **deltas vs. Pilot 1** ([02](02-rrc-pilot-connection-establishment.md)); the
worked-instance method is the same.

---

## 1. The procedure has a fundamentally different shape

Connection establishment was **exchange-shaped** (a fixed message handshake). Reconfiguration is
a **dispatcher**: `RRCReconfiguration` is a container of *optional* sub-configurations
(`radioBearerConfig`, `secondaryCellGroup`, `measConfig`, `masterCellGroup`,
`reconfigurationWithSync`, `conditionalReconfiguration`, …) and the procedure body is almost
entirely *"if the message includes IE X, perform sub-procedure Y"*. This shape difference is the
source of every new finding below.

## 2. New findings → schema growth

### A. IE **presence semantics** are deterministic and first-class
The ASN.1 carries 3GPP's formal presence annotations:
`-- Need M`, `-- Need N`, `-- Need S`, `-- Cond SCG`, `-- Cond LTM`, plus `OPTIONAL`. These are
machine-extractable (Layer C, high confidence) and behaviorally load-bearing.
→ **`CONTAINS` / IE nodes get attributes:** `presence` (mandatory|optional), `needCode`
(M|N|S|R), `conditionalPresence` (the `Cond <tag>` name). Not just "is it there" — *under what
condition*.

### B. **Conditional invocation** — `INVOKES` needs a guard
"if RRCReconfiguration includes `masterCellGroup` → perform cell group configuration (5.3.5.5)";
"if includes `masterKeyUpdate` → AS security key update (5.3.5.7)"; etc. The invocation is
**gated by the presence of a specific IE**.
→ **`INVOKES` gains a `guard` attribute** (e.g. `guard = "presence of IE masterCellGroup"`). This
is the dominant edge type in 5.3.5.

### C. **New entity type: `UEVariable`**
The specs define named UE state stores — `VarConditionalReconfig`, `VarRLF-Report` (also seen in
Pilot 1), `VarAppLayerIdleConfig`. Procedures read/write them ("remove all entries in
condReconfigList within … VarConditionalReconfig"; "the UE maintains two independent
VarConditionalReconfig"). These are recurring and first-class.
→ **Add `UEVariable` entity type** + relationships **`READS` / `WRITES`** (Procedure→UEVariable).

### D. **Timers are configured by IEs** — new `CONFIGURES` edge
`ReconfigurationWithSync` carries `t304 ENUMERATED {ms50, ms100, … ms10000}` — the **value of
Timer T304 is delivered inside the message**, and T304 then governs reconfiguration-with-sync;
its expiry (5.3.5.8.3) is the failure trigger.
→ **Add `CONFIGURES` (IE→Timer)** and confirm **`GOVERNS` (Timer→Procedure)**. (Pilot 1's timers
were started/stopped with fixed identity; here a timer's *value* is carried by an IE.)

### E. **Failure semantics are richer** — generalize alternative outcomes
"Inability to comply" (5.3.5.8.2) → revert to prior config + invoke **SCG failure information
(5.7.3)** or **re-establishment (5.3.7 / TS 36.331)**. `T304`/`T420` expiry (5.3.5.8.3) → release
target resources. Pilot 1's `ALTERNATIVE_OUTCOME` (→RRCReject) is the simple case of this.
→ **Add `ON_FAILURE_INVOKES` (Procedure→Procedure)**; failure **Events** (`T304 expiry`,
`T420 expiry`, `inability to comply`) carry the consequence edges.

### F. **Cross-layer `ACTS_ON`** — the procedure manipulates other layers
"re-establish the RLC entity (TS 38.322)", "reconfigure the PDCP entity (TS 38.323)", "reset MAC".
The RRC procedure acts on **MAC / RLC / PDCP** entities owned by other layers/specs.
→ **Add `ACTS_ON` (Procedure→ProtocolLayer)**, tagged cross-spec via the existing `REFERENCES`
provenance. **Granularity decision:** do *not* instantiate per-entity nodes ("the RLC entity for
SRB1") — model the layer-level action; the exact entity logic stays in the linked prose.

## 3. Granularity principle — sharpened (asymmetric)

Pilot 1 said "index, don't re-encode." 5.3.5 sharpens it: **the restraint is asymmetric.**

- **Layer C (ASN.1 containment)** is deterministic, cheap, and high-value → **fully materialize**
  the `CONTAINS` tree, even deep (`CellGroupConfig`, `RadioBearerConfig`, `MeasConfig` sub-trees),
  with presence attributes (finding A).
- **Layer D (behavioral prose)** is fuzzy and explosive → **stay selective**: materialize only the
  salient typed edges that answer a competency question (INVOKES, STARTS/STOPS, TRANSITIONS_TO,
  ACTS_ON, READS/WRITES). The ~hundreds of nested conditional `shall` steps stay in the prose,
  reached via `DEFINED_IN`.

## 4. Open modeling question (do **not** resolve yet)

**Procedure modes/variants.** Reconfiguration-with-sync has many cases — key-refresh,
DAPS (dual-active), LTM cell switch, direct/indirect path switch. Are these distinct `Procedure`
instances, or *modes* of one procedure (an attribute / sub-procedure)? Defer until a slice forces
it; lean toward "mode attribute on the INVOKES/Procedure" to avoid node explosion. Logged here so
we don't silently pick one.

## 5. Updated seed schema (delta from Pilot 1)

**Entity types (＋1):** ProtocolLayer · Procedure · Message · InformationElement · Timer · State ·
Event · Condition · Capability · Bearer · **UEVariable** *(new)*. *(Channel, Identity, ProtocolEntity
still deferred.)*

**Relationship types (＋4):** … (Pilot-1 set) … ＋ **CONFIGURES** · **ON_FAILURE_INVOKES** ·
**READS** · **WRITES** · **GOVERNS** *(confirmed)* · **ACTS_ON**.

**New attributes:** IE/`CONTAINS`: `presence`, `needCode`, `conditionalPresence`. `INVOKES`: `guard`.

> Consistent with the agreed stance: the schema is an **extensible seed**; this slice added
> `UEVariable` + 5 relationship types + presence/guard attributes because competency questions
> (conditional config application, failure handling, conditional execution) demanded them.

## 6. Confirmations (what held from Pilot 1)

- Two-hierarchy + `DEFINED_IN` join: held.
- Shared sub-procedures (cell group config 5.3.5.5, radio bearer config 5.3.5.6) are **invoked by
  both** setup and reconfiguration → single shared node, never duplicated. Reinforced.
- Per-edge `modality` + `confidence` tagging: even more valuable here (deterministic presence
  attributes vs. fuzzy failure-cascade edges).

## 7. Next

- **Pilot 2 — IMS (TS 24.229)**: prose-only stress test (no ASN.1 backbone; SIP-based). Expect the
  asymmetric granularity rule (finding §3) to lose its deterministic half — the real test of
  whether the behavioral-edge discipline holds without an ASN.1 anchor.
- After IMS: assess whether the seed schema is stable enough to promote to `DECISIONS.md` and begin
  formal requirements.
