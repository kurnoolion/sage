# Design scratch pad

**Status**: living working notes — NOT authoritative. This is the running capture of *all* our
design discussions and explanations; we distill it into the formal design doc when ready.
Terse decisions live in `docs/compact/DECISIONS.md` (D-001…); phase-0 findings in
`docs/research/01–04`; the runnable baseline in `rrc-pilot/README.md`. This pad keeps the
**reasoning and explanations** in one place.

## Contents
- A. Project & approach (1–3)
- B. Conceptual model — the explanations (4–10)
- C. Artifacts, schema & invariants (11–13)
- D. Versioning & change tracking (14–15)
- E. Extraction pipeline (16)
- F. Open decisions & risks (17)
- G. Decision index (18)

---

# A. Project & approach

## 1. What we're building / scope  [D-001]
A **taxonomy + knowledge graph of UE-related 3GPP specifications** — and the corpus behind it.
Deliverables are **data artifacts**, not an app. The MNO device-requirements Q&A bot (the original
motivation) and any serving runtime are **out of scope**. UE-relevance is the standing filter.
Possible future extension to GSMA / OMA / IETF (the concept scheme is the hub that makes that clean).

## 2. Prior work (lit review highlights)  [docs/research/01]
- Existing 3GPP/telecom KG work is **RAG-first, not taxonomy-first** — KGs built to boost a bot,
  so the ontologies are shallow/partial. A clean, validated UE taxonomy-as-artifact is the gap.
- **UE-vs-network split is essentially unaddressed** (Telco-oRAG even says so).
- Reusable from others: series-numbering as a corpus axis, typed nodes + provenance metadata,
  hybrid deterministic+LLM extraction with triple validation, TSpec-LLM corpus, TeleQnA eval.
- Not reusable: their ontologies (wrong WG — SA2/SA5, not RAN2/CT1; retrieval-shaped).

## 3. Pilots & method
- **RRC pilot** (TS 38.331): hand-curated a small KG from clauses **5.3.3** (connection
  establishment) and **5.3.5** (reconfiguration) to *validate the schema/method*, not to be
  complete. This produced the seed ontology and the granularity findings.
- **IMS pilot** (TS 24.229): entire spec ingested into the corpus (2096 clauses, 488 tables,
  6 MB). KG extraction is the upcoming pipeline (can't hand-author a 1000-page prose spec).
- Method: hand-curate → validate schema → build extraction pipeline for scale.

---

# B. Conceptual model — the explanations

## 4. The three layers  [D-003]
| | **Ontology** | **Knowledge graph** | **Corpus** |
|---|---|---|---|
| Role | the **schema** | the **data** | the **source** |
| Holds | entity *types*, relationship *types* (`domain→range`), `subtype_of`, attributes | *instances* + typed relationships, **text-free**, with provenance refs | complete **verbatim** clause text (prose + ASN.1/tables), addressable |
| Answers | "What **can** exist & relate?" | "What **does** exist & relate, and where?" | "What does the spec **actually say**?" |
| Churn | small, stable | grows with each fact | fixed per spec version |

**One fact across all three** (`RRC connection establishment starts T300`):
- Ontology: `Procedure`,`Timer` types + rule `STARTS: Procedure→Timer` (never names T300).
- KG: `P_setup(Procedure) --STARTS--> T_t300(Timer)`, modality=prose, prov→clause 5.3.3.2 anchor "start timer T300" (no prose stored).
- Corpus: clause 5.3.3.2 verbatim "…start timer T300…" (no notion of STARTS/Procedure).

Connections: **KG→Ontology** (every `type` declared; endpoints obey `domain/range`) and
**KG→Corpus** (provenance resolves). Both are enforced (see §13).

## 5. Taxonomy vs ontology
A **taxonomy** is just a hierarchy (mostly is-a / broader-narrower). An **ontology** is the
hierarchy **plus** arbitrary typed relationships (domain→range), attributes, and rules — it lets
you *reason*, not just classify. So **an ontology contains a taxonomy**: a taxonomy is "an
ontology with only is-a edges." → We folded the **type hierarchy into the ontology** (`subtype_of`,
root `Entity`); there is no separate "type taxonomy" file. [D-004]

## 6. Ontology vs KG
- **Ontology = schema (TBox)**: the *kinds* of things and *kinds* of links. Small, stable.
- **KG = data (ABox)**: the *specific* things and links, with provenance. Large, grows.
- Analogies: schema:rows, class:objects, grammar:sentences, legend:map.
- The seam: every instance's `type` (instance-of) points back to the ontology; the
  `domain/range` check is that relationship made operational. `P_setup —STARTS→ T_t300` is *valid*
  only because the ontology declares `STARTS: Procedure→Timer`.
- Subtlety: the **concept scheme** blurs the line — concepts (`RRC`) are KG *instances* of
  ontology types yet act as schema-like vocabulary (normal for SKOS).

## 7. Should 100% verbatim prose be in the ontology/KG?  — No  [D-003]
Two goals with opposite success criteria: **structured reasoning** (ontology/KG — inherently
*selective/lossy*; abstraction is the value) vs **retrieval of exact normative text** (corpus —
*complete/verbatim*; for a compliance-grade spec the exact words are load-bearing). One artifact
can't serve both. **Losslessness comes from the KG *linking* to the complete corpus, not from
encoding prose as graph.** Coverage targets: ~100% **text** coverage in the corpus; ~100%
**conceptual** coverage (vs competency questions) in the ontology/KG. Chasing text coverage in the
KG is a non-goal and the way these projects drown.

## 8. The three hierarchies (don't confuse them)  [D-004]
| Hierarchy | Organizes | File | Tree edge | In ontology? |
|---|---|---|---|---|
| **Type** | kinds of entities | `ontology/ontology.json` | `subtype_of` | **Yes (folded in)** |
| **Domain** (concept scheme) | the protocol stack | `concept-scheme/domain-concept-scheme.json` | `broader` | No (adjunct) |
| **Document** (corpus index) | the spec's structure | `corpus-index/document-index.json` | `parent` | No (pairs w/ corpus) |

- **Type**: `Entity → Procedure/Message/Timer/…` via `subtype_of`.
- **Domain example**: `C_RRC(type ProtocolLayer) broader C_AS broader C_UE`; `P_setup IN_LAYER C_RRC`.
- **Document example**: `3GPP/RAN2 → series 38 → 38.331 → 5 → 5.3 → 5.3.3 → 5.3.3.2 "Initiation"`.

## 9. Domain concept scheme (DCS)
- **What**: curated SKOS-style protocol stack `UE → AS/NAS → RRC/MAC/…/IMS`. Each concept is a KG
  **instance** typed by the ontology (`RRC` is a `ProtocolLayer`, `AS` a `Stratum`).
- **Why**: the stable **cross-release / cross-SDO hub** — the join point for adding NAS/IMS/other
  SDOs; the primary faceting axis.
- **How connected**: ontology **types** each concept; KG entities attach via **`IN_LAYER`**;
  concepts nest via **`BROADER`**; document index maps spec→concept.
- **How used**: faceted navigation/scoping ("all RRC procedures"), cross-spec anchoring, roll-up
  reasoning (by stratum), and grounding/validation of extracted triples.
- Viewable as a top-down tree: `rrc-pilot/viz/concept-view.html` (each concept shows its
  `IN_LAYER` count + v1-scope).

## 10. Granularity principle (asymmetric) + modality/confidence  [D-005]
The KG **indexes** the specs, it does not **re-encode** them. Restraint is **asymmetric**:
- **Layer C (ASN.1 containment)** — deterministic, cheap → **fully materialize** (even deep), with
  presence attributes (`Need M/N/S`, `Cond …`).
- **Layer D (behavioural prose)** — fuzzy, explosive → **selective**; materialize only edges that
  answer a competency question; the exact nested `shall` logic stays in the linked corpus.
Every edge carries `modality` (asn1/prose/curated) + `confidence`. **Competency questions are the
test** for whether an edge earns its place. (Discovered on RRC 5.3.3/5.3.5; IMS is prose-only so
the deterministic half largely vanishes — the real test of the discipline.)

---

# C. Artifacts, schema & invariants

## 11. Artifact layout & commit policy  [D-009]
| Artifact | Path | Committed? |
|---|---|---|
| Corpus store (verbatim clauses + tables, per version) | `corpus/store/<spec>-<ver>/clauses.json` | No (3GPP copyright) |
| Document index (structure, per version) | `corpus/store/<…>/document-index.json` (RRC's at `rrc-pilot/corpus-index/`) | structure only |
| Ontology (TBox) | `rrc-pilot/ontology/ontology.json` | Yes |
| Concept scheme (DCS) | `rrc-pilot/concept-scheme/domain-concept-scheme.json` | Yes |
| Knowledge graph (ABox) | `rrc-pilot/knowledge-graph/kg.json` | Yes (short anchors only) |
| Tooling | `corpus/build_corpus.py`, `rrc-pilot/build_layers.py`, `rrc-pilot/viz/*.py` | Yes |
| Generated viewer HTML | `rrc-pilot/viz/*.html` | No (embeds prose) |

- Single source of truth for the RRC pilot facts: `rrc-pilot/rrc_model.py`; `build_layers.py`
  compiles + validates + regenerates views. Corpus rebuilt from public specs via `build_corpus.py`.
- **Store-agnostic JSON** for now [D-007] — doesn't prejudge RDF/SKOS vs property graph.
- *Note (open)*: multi-spec layout — `rrc-pilot/` is RRC-named; the doc index lives in two
  conventions (RRC under `rrc-pilot/corpus-index/`, IMS under `corpus/store/`). Reconcile into a
  shared multi-spec layout (`specs/<spec>/…` + shared global `ontology/`, `concept-scheme/`).

## 12. Schema seed (current — extensible) [D-006]
**Entity types (15)**: Entity (root) · DomainRoot · Stratum · ProtocolLayer · Procedure · Message ·
InformationElement · Timer · State · Event · Condition · Capability · Bearer · UEVariable · Release.
**Relationship types (24)**: DEFINED_IN · CONTAINS · HAS_DOMAIN · EXCHANGES · REUSED_BY · STARTS ·
STOPS · TRANSITIONS_TO · HAS_PRECONDITION · TRIGGERS · ALTERNATIVE_OUTCOME · ESTABLISHES · INVOKES ·
ON_EXPIRY_OF · CONFIGURES · GOVERNS · READS · WRITES · ACTS_ON · ON_FAILURE_INVOKES · IN_LAYER ·
BROADER · NEXT_RELEASE · SUPERSEDES.
**Edge attrs**: modality, confidence, + relation-specific (direction, optional/needCode, guard, role).
**Expected IMS additions**: NetworkElement/Role (UE, P-/S-/I-CSCF…), SIPMethod, SIPHeader,
IdentityType, SIP timers. (Seed grows per spec; that's normal, not drift.)

Schema-growth history (evidence it's working): RRC 5.3.3 → seed; 5.3.5 → +UEVariable, +CONFIGURES,
ON_FAILURE_INVOKES, READS, WRITES, ACTS_ON, IE presence attrs, INVOKES guard; layer refactor →
+IN_LAYER/BROADER; versioning → +Release/NEXT_RELEASE/SUPERSEDES + lifecycle fields.

## 13. Validation invariants  [D-008]
Build must pass, zero errors:
- **KG ⊨ ontology** — every entity/relation type declared; every relation's `from`/`to` obey the
  declared `domain`/`range`.
- **KG ⊨ corpus** — every (non-curated) provenance entry's clause resolves and its anchor locates
  in that clause's text (incl. named ASN.1 sub-units like `6.2.2/RRCSetupRequest`).
- **Release fields** — `observed_in`/`introduced_in`/`valid_until` ∈ known releases; `supersedes`
  refs an existing id.
These double as the **hallucination guardrail** for automated extraction (non-conforming triples
rejected/queued).

---

# D. Versioning & change tracking

## 14. Multi-release model  [D-011]
Shared identity + versioned assertions (NOT separate graphs):
- **Release-agnostic identity** — node id is semantic (`type+name+layer`), never the clause number.
- **`Release` is first-class**, ordered via `NEXT_RELEASE`.
- **Every entity/relation release-stamped**: `observed_in`, `introduced_in`, `valid_until`
  (null=current), `supersedes`. Unchanged facts stored once with an open range → size O(distinct
  facts), not O(facts × releases).
- **Provenance is a per-version list** `[{release, spec, version, clause, anchor}, …]` — clause
  recorded per version, so **renumbering is captured**, identity independent of clause number.
- **Time-varying attributes = sets of immutable value-assertions** (SCD-2); all prior values kept.
- **Lifecycle is computed, not extracted** (see §15).

**Example (real field — `rach-LessHO-r18` inside `ReconfigurationWithSync`).** The `-r18` suffix
shows it appeared in Rel-18; the same node persists into Rel-19 with per-version provenance:
```json
// entity (one node, semantic identity)
{ "id":"IE_rachLessHO", "type":"InformationElement", "label":"rach-LessHO",
  "defined_in":[{"release":"Rel-18","spec":"TS 38.331","version":"18.x","clause":"6.3.2/ReconfigurationWithSync"}],
  "observed_in":["Rel-18","Rel-19"], "introduced_in":"Rel-18", "valid_until":null, "supersedes":null }

// relation: ReconfigurationWithSync CONTAINS rach-LessHO  (per-version provenance list)
{ "id":"r_rws_rachLessHO", "type":"CONTAINS", "from":"IE_reconfigwithsync", "to":"IE_rachLessHO",
  "modality":"asn1", "confidence":"high", "attrs":{"presence":"Need N"},
  "provenance":[ {"release":"Rel-18","version":"18.x","clause":"6.3.2/ReconfigurationWithSync","anchor":"rach-LessHO-r18"},
                 {"release":"Rel-19","version":"19.2.0","clause":"6.3.2/ReconfigurationWithSync","anchor":"rach-LessHO-r18"} ],
  "observed_in":["Rel-18","Rel-19"], "introduced_in":"Rel-18", "valid_until":null, "supersedes":null }
```
Contrast `t304` (no suffix): present since the start of our window → `introduced_in:"Rel-15"` with
`introduced_at_floor:true` (we can't see before our earliest ingested release).

## 15. Change-tracking / derivation model  (proposed D-012)

### 15.1 Foundation — two commitments everything rests on
**(a) Deterministic semantic keys**: entity `type|canonical-name|layer`; relation
`from|predicate|to[|role]` (attrs like guard/value are versioned, not in the key); attribute
timeline `(owner-key, attr)`; assertion id content-derived (`owner|attr|valid_from`).
**(b) Snapshots are the source of truth; the unified KG is a derived projection** (event-sourcing):
```
extract(version) → snapshot[(spec,version)]   (immutable, append-only)
alias-map, review-decisions ─┐
                             └→ derive() → unified KG (lifecycle + assertions, deterministic ids)
```
The unified KG is never hand-mutated; it's recomputed. This gives order-independent diffs,
idempotent re-ingest, minimal churn.

**Example (keys + one snapshot).**
```
entity key     Timer|T300|RRC            Message|RRCSetupRequest|RRC      InformationElement|rach-LessHO|RRC
relation key   Procedure|RRC connection establishment|RRC | STARTS | Timer|T300|RRC
attr timeline  (Timer|T304|RRC, value_domain)        assertion id: "Timer|T304|RRC|value_domain|Rel-18"

snapshot[TS 38.331, 18.x] = {
  entities:  { Timer|T300|RRC, Message|RRCSetupRequest|RRC, InformationElement|rach-LessHO|RRC, ... }
  relations: { ReconfigurationWithSync CONTAINS rach-LessHO, RRC-conn-establishment STARTS T300, ... }
  attr_obs:  { (Timer|T304|RRC, value_domain): "{ms50,ms100,ms150,ms200,ms500,ms1000,ms2000,ms10000}" }
  provenance: per key → its clause in v18.x
}
```
`derive([snapshot_Rel15, …, snapshot_Rel19], alias_map, review_decisions)` folds these into the
unified KG. Note `rach-LessHO` is *absent* from the Rel-15/16/17 snapshots and *present* from Rel-18 —
that presence boundary is what §15.2 turns into `introduced_in:"Rel-18"`.

### 15.2 Computing introduced_in / removed_in / supersedes
Walk releases ascending, reconcile by key.
- **Presence**: key new → `introduced_in=N`; in both → append `observed_in`; gone in N →
  `removed_in=N`, `valid_until=N-1`.
- **Value** (per `(owner,attr)` with value v_N): new → open; equal → extend; **changed → close
  current (valid_until=N-1) + open new (supersedes=prev)**. A→B→A = 3-link chain (correct).
- Caveats: `introduced_in` at the earliest ingested release is a **lower bound** (flag
  `introduced_at_floor`); **absence ≠ removal** — prefer explicit "Void"/change-marks; low-confidence
  disappearance → review.

**Example — presence walk for `rach-LessHO` across snapshots:**
```
Rel-15: absent   Rel-16: absent   Rel-17: absent   Rel-18: PRESENT   Rel-19: present
                                                    └─ new key ──────┘
derive ⇒ introduced_in=Rel-18, observed_in=[Rel-18,Rel-19], valid_until=null
```
**Example — removal via explicit "Void" (real pattern):** clause `5.3.3.1b` is literally titled
**"Void"** in v19. If a procedure that existed in Rel-17 has its clause marked Void in Rel-18:
```
Rel-17: present   Rel-18: clause says "Void"  ⇒ removed_in=Rel-18, valid_until=Rel-17
```
(detected from the explicit "Void" signal, not merely from absence — which could be an extraction miss).

### 15.3 Value-assertions — keying/merging (SCD-2)
Timeline `(owner, attr)`; collect per-release `release→value`, sort, **coalesce consecutive equal
values into segments** (`valid_from..valid_until`) — coalescing *is* the merge. Each segment carries
its own provenance list. Needs a **value-normalization** fn per attr type (enum=set, timer=numeric)
or you get false changes. Same for relation attributes (changed guard = value-assertion, not new edge).

**Example — `T304` value_domain coalesced into segments** (illustrative enum growth: a value added
in Rel-18):
```
per-release observations of (Timer|T304|RRC, value_domain):
  Rel-15→S1   Rel-16→S1   Rel-17→S1   Rel-18→S2   Rel-19→S2
  where S1={ms50,ms100,ms150,ms200,ms500,ms1000,ms2000,ms10000}
        S2=S1 ∪ {ms5000}

coalesce consecutive-equal ⇒ two value-assertions:
  A1 value=S1 valid Rel-15..Rel-17  supersedes —   provenance:[Rel-15 §…, Rel-16 §…, Rel-17 §…]
  A2 value=S2 valid Rel-18..(open)  supersedes A1  provenance:[Rel-18 §…, Rel-19 §6.3.2/ReconfigurationWithSync]
```
Query "T304 domain at Rel-16" → A1 (S1); "current" → A2 (S2); "history" → A1→A2. Note Rel-15/16/17
are **one** segment (coalesced), not three. A relation example: `INVOKES.guard` on
`RRCReconfiguration INVOKES cell-group-config` changing wording across releases would version the
same way — a new guard value-assertion, not a new INVOKES edge.

### 15.4 Churn-free re-ingestion of corrected versions
Re-ingest = **replace that one `(spec,version)` snapshot** → re-derive. **Content-derived ids +
sorted output** ⇒ unchanged facts serialize byte-identically ⇒ diff shows only real changes.
**Representative version per release** (latest within release) for provenance; corrections update
that entry + changed facts; sub-release churn doesn't leak into release-level lifecycle.

**Example — re-ingest a Rel-19 correction (v19.2.0 → v19.3.0) that fixes a typo in clause 5.3.3.2:**
```
1. replace snapshot[TS 38.331, 19.2.0]  with  snapshot[TS 38.331, 19.3.0]   (idempotent by key)
2. re-derive()

fact r_setup_starts_T300 — id is content-derived, UNCHANGED:
  before: provenance:[{Rel-19,"19.2.0","5.3.3.2","start timer T300"}]
  after:  provenance:[{Rel-19,"19.3.0","5.3.3.2","start timer T300"}]   ← only the version bumped
every other fact: byte-identical (deterministic ids + sorted output)
git diff: ~the one changed clause's facts. No reshuffle, no churn.
```
If the correction had *changed* T300's start condition, that would be a value/relation change →
supersede (§15.2), still localized to that fact.

### 15.5 Review queue — renames & ambiguous merges
Presence diff naively reads a rename as remove+add (severs identity). A **detector** matches a
disappeared key against new keys via: label similarity, same type+layer, **structural overlap**
(shares most edges — strongest), adjacent clause, explicit signals (`-rNN`, documented renames).
**Never auto-merge identity** — emit a **review item** (confirm-rename / keep-separate / split /
merge). Human decision → **durable alias/decision file** feeding the next `derive()` (recorded once;
never re-asked). On confirm: collapse to one identity, inherit `introduced_in`, add
`renamed_in`/`aka`. Same queue: value conflicts, splits/merges, low-confidence LLM triples.

**Example — rename detected, review-gated** (illustrative): a procedure key disappears in Rel-18
while a similar one appears, sharing most edges:
```json
// review/ item emitted by derive()
{ "kind":"possible-rename", "release":"Rel-18",
  "gone":"Procedure|conditional reconfiguration foo|RRC",
  "new" :"Procedure|conditional reconfiguration|RRC",
  "similarity":0.91, "shared_neighbours":"7/8",
  "signals":["label-edit-distance","structural-overlap","adjacent-clause"],
  "options":["confirm-rename","keep-separate","split","merge"] }
```
```yaml
# durable alias/decision file (human-curated, feeds the NEXT derive())
- action: confirm-rename
  from: "Procedure|conditional reconfiguration foo|RRC"
  to:   "Procedure|conditional reconfiguration|RRC"
  renamed_in: Rel-18
```
```json
// resulting unified node after re-derive — one identity, history preserved
{ "id":"P_condreconfig", "type":"Procedure", "label":"Conditional reconfiguration",
  "aka":["conditional reconfiguration foo"], "renamed_in":"Rel-18",
  "introduced_in":"Rel-16", "observed_in":["Rel-16","Rel-17","Rel-18","Rel-19"] }
```
Without the alias, the naive diff would have wrongly recorded `…foo` as `removed_in:Rel-18` and the
new key as a fresh `introduced_in:Rel-18`, severing the edges/history. **Conflict example**: if two
Rel-18 snapshot facts canonicalize to the same `(s,p,o)` but disagree on an attribute value, derive()
emits a `value-conflict` review item instead of silently picking one.

---

# E. Extraction pipeline

## 16. Approach  [D-010]
Curated **gold seed** of example facts per doc + a **few-shot prompt** (examples + ontology + clause
text → schema-valid JSON triples); **deterministic pass first** (clause graph, cross-refs, SIP
vocab, tables, roles) to provide canonical anchors; **on-prem local model** (OpenAI-compatible
endpoint) does the behavioural prose extraction over **UE-relevant** clauses; outputs **validated**
(§13), **deduplicated/entity-resolved**, low-confidence → **review queue**. Gold seed doubles as the
precision/recall eval set. One shared ontology; per-doc examples + prompt; model-agnostic client.
Pipeline shape:
```
per-release:  UE filter → deterministic extractors → LLM extractor → validate → snapshot
cross-release: derive(snapshots, alias-map, review-decisions) → unified KG + review items + views
```
Division of labour: human owns schema/examples/prompt/validation; on-prem compute owns volume.

---

# F. Open decisions & risks

## 17. Open / to-lock
- **D-007** store choice (RDF/SKOS vs property graph) — defer until schema stabilizes across
  RRC+IMS. Versioned facts: edge-properties (PG) vs reification/named-graphs-per-release (RDF).
- **D-012** change-tracking/derivation model (this §15) — record when pipeline starts.
- **`-rNN` suffix handling** — lean: keep suffixed name as canonical id; read suffix as
  `introduced_in` signal; collapse only via review/alias.
- **Value-normalization** functions per attribute type.
- **Removal-detection** policy (explicit Void/change-mark vs absence + confidence).
- **Representative-version** policy (latest-in-release).
- **`introduced_at_floor`** flag adoption; **rename-similarity floor** + signal weighting.
- **Multi-spec repo layout** (§11 note) — shared `specs/<spec>/` + global ontology/concept-scheme.
- **Procedure modes vs variants** (RRC reconfig-with-sync cases) — research 03 §4.
- **Stakeholder map / domain-validator + eval-data channels** — still TODO (PROJECT.md Open Qs).

### Risks
- Name canonicalization (suffixes/abbrevs/synonyms) — main source of bad merges → review.
- Absence-as-removal unreliable → explicit signals + confidence.
- Value-normalization sloppiness → false history.
- Entity resolution at scale (structural matching over many nodes) must be efficient.
- `introduced_in` only a lower bound until earliest relevant release ingested.
- IMS is prose-only (no ASN.1 backbone) → behavioural-edge discipline under maximal stress.

---

# G. Decision index
- **D-001** UE-focused taxonomy+KG; bot out of scope
- **D-002** two hierarchies joined by DEFINED_IN
- **D-003** three-layer separation; 100% text only in corpus
- **D-004** type hierarchy folded into ontology; concept-scheme + corpus-index adjuncts
- **D-005** granularity principle (asymmetric) + modality/confidence
- **D-006** extensible seed schema
- **D-007** store-agnostic now; store choice deferred *(open)*
- **D-008** validation invariants (KG ⊨ ontology, KG ⊨ corpus)
- **D-009** corpus copyright / commit policy
- **D-010** extraction: curated seed + few-shot + on-prem model
- **D-011** multi-release: shared identity + versioned assertions + per-version provenance
- **D-012** change-tracking / derivation model (§15) — *Active*
- **D-013** NORA integration contract — anchor+augment; id-alignment; delta-classification↔NORA edges; per-release projection (§H) — *Active (drafted)*
- **(planned)** risk-monitoring auditor (§I)

*(Full text in `docs/compact/DECISIONS.md`.)*

---

# H. NORA integration (feasibility — in progress)

**Goal**: make this 3GPP KG the **substrate** for `~/work/nora` (NORA — Network Operator
Requirements Analyzer), whose KG of **MNO device requirements** groups/compares requirements by
the 3GPP entity they concern (e.g. "IMS Registration"), across MNOs and across MNO-doc releases
(Feb2026, Oct2025). Verdict so far: **highly feasible — the designs already converge**; this is
integration + id-alignment, not invention.

## H.1 What NORA already is (grounded read)
Mature PoC (KG + RAG, local Ollama/Gemma, web UI, metrics). TDD §4.2 chose a **single unified
graph, partitioned by `mno`+`release` metadata**, *because* cross-MNO and cross-release comparison
are first-class. Pipeline: extract → profile → parse → resolve → **feature taxonomy** →
**standards ingestion** → **KG build** → vectorstore → query → eval.

**NORA KG schema** (`core/src/graph/schema.py`, NetworkX DiGraph):
- Nodes: `MNO`, `Release` (`release:VZW:2026_feb`), `Plan`, `Requirement`,
  `Standard_Section` (`std:24.301:11:5.5.1.2.5` = spec:release_num:section), **`Feature`
  (`feature:IMS_REGISTRATION`)**.
- Edges: `references_standard` (Req→Std_Section), **`maps_to` (Req→Feature)**, `has_release`, …
- `Feature` is **MNO-agnostic** with `mno_coverage:{VZW:[…],TMO:[…],ATT:[…]}` — *exactly* the
  group/compare mechanism. Currently **LLM-derived bottom-up** from MNO-doc TOCs + human review (§5.7).

**NORA already builds corpus + doc-index too**: `standards/` is *fully generic* — collects 3GPP
refs from MNO docs → `reference_index.json` (the citation index of `(spec, release, sections)`) →
downloads from 3GPP FTP → `spec_parsed.json` (full **section tree**) + `sections.json`. Treats each
`(spec, release, section)` as an **immutable, duplicated** node ("a 3GPP section doesn't change").

## H.2 Convergence (our design ↔ NORA)
| Concept | This project | NORA |
|---|---|---|
| Cross-MNO/-release comparison | (downstream goal) | first-class, unified graph + metadata [§4.2] |
| Grouping anchor | concept scheme + Procedure entities | `Feature` + `maps_to` (LLM-derived) |
| 3GPP section | corpus clause `(spec,ver,clause)` + document-index | `Standard_Section` `std:spec:rel:section` + `spec_parsed.json` |
| Spec corpus/parse | `corpus/build_corpus.py` (incl. tables) | `standards/` generic download+parse |
| MNO-doc versioning | (D-011 machinery generalizes) | `Release` nodes (Feb2026/Oct2025) |

## H.3 Our distinctive value over NORA's standards/taxonomy
NORA already has section trees + a flat feature list. We add the **deep semantic layer between them**:
1. **Rich entity model** (Procedure/Message/IE/Timer/State) *under* each section — NORA has only section text.
2. **Concept scheme** (cross-spec/SDO hub) — NORA's features are flat + MNO-derived.
3. **Rigorous multi-release change-tracking** (introduced/removed/supersedes, renames) — NORA treats sections as immutable per release.
4. **Validation invariants + provenance discipline** (KG ⊨ ontology / corpus).

## H.4 Plug-in points + id alignment (the contract to nail)
- `feature:IMS_REGISTRATION`  ↔  our `C_IMS` concept and/or `Procedure|…registration…|IMS`.
- `std:24.229:19:5.1.1.2`  ↔  our corpus clause `(24.229, Rel-19, 5.1.1.2)` + entities `DEFINED_IN` it.
- Reconcile NORA `release_num` (int 19) ↔ our `Rel-19` / `version 19.6.0` → **align at release level**.
- Upgrade: comparison moves from "both cover IMS registration" → "MNO-A overrides timer T in
  initial registration (Rel-17 §5.1.1.2.2); MNO-B sets IE Y" (because we have the entities).

## H.5 Strongest concrete insight (bidirectional)
NORA's **`reference_index.json` drives our spec/section prioritization** — model what the MNO corpus
actually cites, in order. **Coverage mismatch to resolve**: sample MNO docs are **LTE-era**
(`24.301` NAS, `36.331`, `24.008`); our pilots are **NR `38.331`** + **`24.229` IMS**. To serve NORA,
re-point spec selection at the citation index (likely add 24.301 etc.).

## H.6 Integration options (boundary)
- **(A) We own the 3GPP pipeline; NORA consumes our KG.** Clean ownership; duplicates NORA's
  download/parse (which already works, generically).
- **(B) We consume NORA's `spec_parsed.json` trees + `reference_index.json`** as corpus input and
  add only the value-add (entities + concept scheme + change-tracking). Avoids duplicate
  download/parse; tighter coupling to NORA's formats.
- Lean: **anchor + augment**, not replace — our KG is the authoritative substrate; NORA's
  `standards/`+`taxonomy/` become **consumers/adapters**; **proprietary MNO features with no 3GPP
  anchor stay in NORA**, flagged. (A) vs (B) is open — (B) is attractive given NORA already parses.

## H.7 Multi-release reconciliation
NORA: immutable per-release section nodes. Us: shared identity + versioned assertions (D-011/D-012).
Resolution: our KG exposes a **per-release projection** that *looks like* NORA's `Standard_Section`
set, **plus** answers "did this change Rel-17→19?" — important when an MNO's Feb-2026 reqs cite a
newer 3GPP release than its Oct-2025 reqs.

## H.8 Confidentiality & store
- **One-way**: NORA imports our **public** 3GPP KG; this repo **never** holds MNO data (VZW PDFs are
  confidential). Keep the substrate public-data-only.
- Store/format: our JSON imports into NORA's NetworkX now; a shared graph DB is a later D-007 input.

## H.9 Open decisions (→ candidate D-013: NORA integration contract)
- Boundary: anchor+augment (confirm); option (A) own-pipeline vs (B) consume-NORA-trees.
- Re-point spec selection at NORA's `reference_index.json` (LTE coverage)?
- Id-alignment contract (feature/section/release_num ↔ our ids); release-level join.
- Per-release projection API for NORA; change-query interface.
- Where the MNO overlay lives (NORA) vs substrate (here) — confirm one-way, no MNO data here.

## H.10 Next reads to finalize the contract
NORA TDD **§6 Knowledge Graph Model**, `core/src/graph/builder.py`, **§7.3 Graph Scoping**,
**§8.3 Compliance Agent**; inspect a real `reference_index.json` + `spec_parsed.json` to lock formats.

## H.11 Resolutions (2026-06-07)

**Boundary — DECIDED: anchor + augment.** Our KG is the authoritative 3GPP substrate; NORA's
`standards/`+`taxonomy/` become consumers/adapters; proprietary MNO features with no 3GPP relation
stay in NORA.

**Requirement→3GPP anchoring — three tiers** (the link *type* carries the meaning):
1. **Spec-behaviour** req (override/change a timer/IE/procedure) → fine-grained **delta** edge
   (`OVERRIDES`/`EXTENDS`/`EXCLUDES`/`MANDATES`) to a *specific 3GPP entity*.
2. **Feature-related** req (UX "turn on VoWiFi in settings"; entitlement "check eligibility";
   enablement on/off) → **associative** edge (`CONCERNS`/`RELATES_TO`/typed `HAS_UX`/
   `GATED_BY_ENTITLEMENT`) to the 3GPP **feature/concept** (VoWiFi) — NOT to a clause/entity.
3. **Purely proprietary** (Android app UI etc.) → **no anchor**; NORA-only.
- Mechanism: NORA `feature:VoWiFi` `maps_to` our concept `VoWiFi`; all tier-1/2 reqs attach to the
  feature → transitively connected. The **concept scheme is the hub for the whole feature surface**
  (spec behaviour + deltas + entitlement + UX) → compare MNOs' *complete* VoWiFi offering.
- Caveats: feature↔concept is **many-to-many/optional** (MNO marketing bundles ≠ one 3GPP construct);
  **entitlement is partly standardised (GSMA TS.43)** → today associative to the concept, **future
  delta to a GSMA entity** once multi-SDO lands (the concept scheme is the multi-SDO hub for exactly
  this). Keep tier-2 links clearly typed so they're never confused with compliance deltas.

**Pipeline ownership — DECIDED: option A.** `3gpp-kg` owns the **entire 3GPP vertical**
(download → parse → corpus → ontology → KG → change-tracking) and becomes a **standalone, general
3GPP knowledge base** (not NORA-dependent). NORA owns the MNO vertical and consumes our outputs.
- **Interface NORA → 3gpp-kg = a plain `(spec, release)` manifest** (NORA derives it from its
  confidential citation index; hands us only the list). **No MNO data crosses into this repo.**
- **Seam refinement**: the truly shared concern is **generic document extraction**
  (PDF/DOC/DOCX → text/structure) — both projects need it → eventually a **shared library**.
  *Download + 3GPP section-parse belong here* (3GPP-specific). Short-term: reuse NORA's `standards/`
  ingest code (vendored, marked for extraction) to move fast; converge on the split later.

**Coverage — DECIDED: driven by NORA's spec list.** We build the KG for the `(spec, release)` set
NORA provides (MNO corpus is LTE-era: 24.301, 36.331, 24.008 …) — likely re-pointing from the
current NR/IMS pilots. Build for **M specs × N releases** from that manifest.

**Mixed-order / sparse ingestion — handled by design.** Snapshots-as-source + order-independent
`derive()` ⇒ ingestion order irrelevant; re-derive on every addition/correction. Refinement for
**non-contiguous releases**: change boundaries are resolved only to the granularity of *ingested*
releases — `introduced_in` is the first **observed** release (a lower bound, `introduced_at_floor`),
self-correcting as earlier releases land; boundaries recorded **relative to `observed_in`**, never
fabricating an exact uningested release. Consumers treat `introduced_in` as observed-set-relative.

**Still open (for the contract, after the NORA deep-read)**: id-alignment (feature/section/
release_num ↔ our ids); the per-release **projection API** NORA consumes; the shared doc-extract
library boundary; where/how delta + associative edges are represented (NORA-side vs shared ontology).

## H.12 Id alignment (design + re-key DONE)

**Real ids.** NORA: `std:24.301:11:5.5.1.2.5` (spec:release_num:section), `feature:IMS_REGISTRATION`,
`release:VZW:2026_feb`, `req:VZ_REQ_..._7748`. Ours **(re-keyed 2026-06-07 from slugs)**:
`3gpp:rrc/procedure/RRC-connection-establishment`, `3gpp:rrc/timer/T300`, `3gpp:concept/ims`,
`3gpp:24.229/Rel-19/clause/5.1.1.2` (clause; representative version in metadata), `3gpp:release/Rel-19`.
`3gpp:` namespace → GSMA/OMA later get `gsma:`/`oma:` and merge cleanly; URI-ready for D-007/RDF.

**Alignment splits into deterministic vs curated:**
| What | NORA | Ours | Join | Kind |
|---|---|---|---|---|
| section/clause | `std:24.229:17:5.1.1.2` | `3gpp:24.229/Rel-17/clause/5.1.1.2` | strip `std:`, release_num→Rel-N | **deterministic** |
| release | `17` (int) | `3gpp:release/Rel-17` | release_num→Rel-N (+ rep-version table) | **deterministic** |
| feature | `feature:IMS_REGISTRATION` | `3gpp:concept/ims-registration` | none | **curated crosswalk** |
| entity | (none) | `3gpp:ims/procedure/initial-registration` | via section→DEFINED_IN | derived |
| **assertion** | (none) | content-derived assertion id (§15.3) | direct ref | **NEW: overrides target these** |

- **Section is the deterministic hinge** — any req citing `(spec, release, section)` reaches our rich
  entities for free. Only **feature↔concept** needs human-curated mapping (small, stable; reuses
  §15.5 alias/review machinery).
- **Our entity layer reconciles NORA's per-release section duplication**: `std:…:17:5.1.1.2` and
  `std:…:19:5.1.1.2` both `DEFINED_IN` → one release-agnostic entity.
- **Option Y chosen**: 3GPP-grounded features adopt our ids (`feature` id = `3gpp:concept/…`);
  proprietary features keep `feature:LOCAL_*`. The id namespace encodes anchored-vs-proprietary.
- release_num↔Rel-N needs a `(spec, release)→representative-version` table; spec `24.301` vs
  `TS 24.301` trivial normalize.
- **New id-alignment requirement**: base **assertions need stable ids** (we have them, §15.3) because
  MNO overrides target a specific base assertion, not just an entity.

## H.13 Requirement-as-delta model (how NORA layers on the base)

**An MNO requirement is a delta operation on the base assertion graph** — the SAME assertion +
supersede + provenance machinery as 3GPP-release versioning, on a **second overlay axis** scoped by
`(MNO, MNO-release)`. "Append to the base KG" = add MNO-scoped assertions on top.

**Three classes (per atomic claim, not per whole requirement):**
1. **CREATE** — no base counterpart → new MNO-scoped assertion (under the concept; tier-2/3 of H.11).
2. **CHANGE/OVERRIDE** — modifies a base assertion → MNO-scoped assertion that **`supersedes`** the
   base assertion *in MNO scope* (delta edge OVERRIDES/EXTENDS/EXCLUDES/MANDATES).
3. **RESTATE** — equals a base assertion → **no new assertion**; a `REQUIRES_COMPLIANCE`/`RESTATES`
   link (compliance evidence for NORA's §8.3 agent).

**Maps onto NORA's existing delta edges** (no new vocabulary needed NORA-side): RESTATE→`defers_to`
(delta null); CHANGE→`overrides` (differ) | `constrains` (narrow); CREATE→`extends` (add beyond) |
pure-new (`maps_to` feature only). The MNO assertion's delta-type *is* the NORA edge type.

**"Follow section X.Y.Z" is context-dependent** (per user): *unconditional* "shall follow §x.y.z" →
RESTATE / `defers_to`; *conditional* "shall follow §x.y.z **when foo**" → **not** a pure restate — it
**adds a precondition** scoping when the base behaviour applies → CHANGE / `constrains` (a
`HAS_PRECONDITION` wrapper over the base assertion). The classifier must read surrounding context, not
just the citation. Prime **risk-auditor** target: a `defers_to` that actually hides a condition.

**Citation = hint, not ground truth.** Anchor = citation-hinted (section→clause→entities) +
text-confirmed (req-text→concept/entity). **Two-fidelity classification**: structured where the base
assertion exists; **prose-fallback** (compare req vs clause prose) otherwise → fidelity is
**coverage-bounded** (argues for deep extraction; enrichment helps).

**Pipeline (NORA, updated):** parse→**claims** · resolve refs (hints) · **candidate retrieval**
(hint + text → base assertions) · **classify** create/change/restate (structured|prose-fallback;
low-confidence→review) · **KG layer** (append MNO assertions referencing base; restate=link) ·
group under our concept ids · **enrichment** (pull base clause prose into req records) · query
(retrieve req + base assertions + base prose → grounded contrastive synthesis).

**Two-axis scope** on every MNO assertion: `(MNO, MNO-release)` + the **targeted 3GPP-release
baseline** + provenance to req *and* base assertion + delta type.

**Boundary**: NORA appends an overlay that *references* our read-only base ids; never mutates the
base. Unified graph = our base (imported) + MNO assertion layers (D-013/A, NORA §4.2).

**Risks**: classification accuracy (RESTATE vs subtle CHANGE is the dangerous confusion → conservative
review); coverage-bounded fidelity; messy claim decomposition; two-axis data complexity.

## H.14 NORA deep-read findings (grounding the contract)

From TDD §6/§7/§8/§9 + `graph/schema.py` + `graph/builder.py` + `standards/schema.py`:
- **KG model** (NetworkX DiGraph): nodes MNO/Release/Plan/Requirement/Test_Plan/Test_Case/
  **Standard_Section**/**Feature**. **Delta edges already exist**: `defers_to` (do what 3GPP says,
  delta null), `constrains` (narrow), `overrides` (differ), `extends` (add) — each with a
  `delta_summary`. Plus `maps_to` (Req→Feature), `version_of` (cross-release req diff:
  added/modified/removed/unchanged), `shared_standard`, `depends_on`.
- **Cross-MNO is via shared Feature/Standard nodes** (no direct cross-MNO edges) — confirms
  concept-as-hub. Example in TDD: `VZW constrains [24.301 §5.5.1 R10]`, `TMO overrides [§5.5.1 R15]`
  — different releases, structured deltas.
- **Query pipeline already pulls standards text into synthesis** (§7.5/§7.6 context templates show
  "Standards: Constrains 24.301 §5.5.1 (R10) / Delta from 3GPP: …" + a "REFERENCED STANDARD" block).
  Our enrichment upgrade = entity-level deltas + verbatim corpus prose + precise provenance.
- **Builder sequence** consumes `*_tree.json`, `*_xrefs.json`, `taxonomy.json`,
  `reference_index.json`, `TS_*/Rel-*/sections.json`. Our KG plugs in at the **standards + feature**
  steps (Standard_Section expansion + authoritative concepts).
- **Eval criteria** (§9.4) already include "standards comparison", "no hallucination (0 fabricated
  reqs)", "standards integration > 80%". → aligns with our risk-auditor.
- Implication: the contract **reuses NORA's vocabulary**; our delta classification = NORA edge types.

---

# I. Risk register & risk-monitoring system

The elegant framing: **each risk maps to an automated check.** Build-time invariants
(KG ⊨ ontology / corpus, D-008) already cover the structural risks; the rest need a dedicated
**post-ingestion risk auditor** that runs after `derive()` and on every re-ingest, emitting a
**risk report (counts + severity)**, **review-queue items**, and **time-series metrics**
(observability). This is "doctor/drift-check for the KG + MNO overlay."

## I.1 Risk register → check

| # | Risk | Layer | Impact | Auditor check |
|---|---|---|---|---|
| R1 | Hallucinated / mis-typed triples | 3GPP KG | wrong facts | KG⊨ontology + anchor-supports-relation sample (LLM-judge/human) + precision/recall vs gold |
| R2 | Bad / missed entity merges (canonicalization) | 3GPP KG | split/merged identity | near-duplicate detector (high sim unmerged) + low-sim-merged audit → review |
| R3 | Absence mistaken for removal | versioning | false `removed_in` | require explicit Void/change-mark; flag inferred removals |
| R4 | Value-normalization false changes | versioning | spurious history | recompute w/ normalizer; flag single-release blips / churn anomalies |
| R5 | Coverage-bounded fidelity | both | weak classification | report % facts structured vs prose-fallback; per-spec coverage |
| R6 | `introduced_in` lower-bound / sparse brackets | versioning | over-precise dates | report which lifecycle fields are floor/bracketed |
| R7 | Provenance anchor drift across releases | corpus link | broken trace | KG⊨corpus per version; flag unresolved anchors |
| R8 | **RESTATE vs subtle CHANGE** misclassification | NORA overlay | missed override / compliance gap | re-diff restate-claims vs base assertion; flag near-misses → review |
| R9 | Conditional "follow §x.y.z" mis-read as plain `defers_to` | NORA overlay | missed precondition | detect conditions inside defers_to-classified claims → should be `constrains` |
| R10 | Citation hint wrong/stale/missing | NORA overlay | mis-anchor | cross-check text-anchor vs citation-anchor; flag mismatches |
| R11 | Feature↔concept crosswalk errors | integration | wrong grouping/compare | orphan features (no concept); implausible MNO spread; sample review |
| R12 | Two-axis scope confusion (MNO-release vs targeted 3GPP-release) | NORA overlay | wrong baseline | verify targeted 3GPP release exists; release ordering sane |
| R13 | Coverage gap: MNO cites spec/section not in our KG | integration | no anchor | diff NORA `reference_index` vs our corpus → gap report (drives ingestion) |
| R14 | Proprietary feature mis-tagged as anchored (or vice versa) | integration | wrong scope | features with citations tagged proprietary, and vice versa |

## I.2 Risk-monitoring system (to design + build)

**TODO — design + build a post-ingestion risk auditor**, run when full data (all specs/releases +
MNO reqs) is ingested and the KGs are built (and on every re-ingest):
- **Inputs**: unified 3GPP KG, MNO overlay, corpus stores, gold set, NORA `reference_index.json`.
- **Checks**: the R1–R14 table above (deterministic where possible; sampling + LLM-judge/human for the
  fuzzy ones R1/R8/R9/R11).
- **Outputs**: (a) a **risk report** (per-check counts + severity, pass/warn/fail); (b) **review-queue
  items** for human adjudication (reuse §15.5 machinery); (c) **metrics over time** (coverage %,
  structured-vs-prose ratio, extraction P/R, #unresolved anchors, #flagged misclassifications) for
  observability/regression tracking.
- **Severity gating**: structural failures (R1 schema, R7 unresolved anchor) = hard fail; fuzzy ones =
  warn + review. Tie thresholds to the eval/observability posture.
- Reuses + extends D-008 validators; conceptually the project's `drift-check`/`doctor` for the
  KG+overlay. Record as its own decision when built.
