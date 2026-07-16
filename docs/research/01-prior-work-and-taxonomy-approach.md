# Phase-0 Research: Prior Work & UE Taxonomy Approach

**Status**: Phase-0 (pre-requirements research). Living document — capture as we explore.
**Last updated**: 2026-07-16 (validation refresh §1.4; TelcoAgent/DeepSpecs deep-read §1.5)
**Scope**: 3GPP **UE-related** specifications only. Goal of the project: a correct,
first-class **taxonomy/ontology** of the UE domain, then a **knowledge graph** on it.
The MNO Q&A bot is out of scope (motivation only).

---

## 1. Literature review — existing 3GPP/telecom taxonomy, ontology & KG work

### 1.1 Headline findings

1. **Prior work is RAG-first, not taxonomy-first.** Almost everyone builds a 3GPP
   knowledge graph *in service of* a Q&A/RAG bot, so the "ontology" is shallow, partial,
   and tuned for retrieval recall — not a rigorous, standalone domain model. → What we
   want to build (a validated UE taxonomy as the primary artifact) is **not redundant**,
   but also has **little prior art to copy** for the hard parts.
2. **The UE-vs-network split is essentially unaddressed.** Telco-oRAG does not model it —
   its treatment of 3GPP structure is series-level retrieval routing, with no UE/network
   distinction anywhere in the paper's framing *(softened 2026-07-16: no "explicit"
   disclaimer was located on re-verification; the split is absent rather than disclaimed)*;
   others organize by publication series, not by UE perspective. → Our UE scoping is
   genuinely under-explored.
3. **The reusable contribution from prior work is architectural, not ontological.** The
   *pipeline patterns* (series-scoped corpus, hybrid deterministic+LLM extraction,
   provenance on every node, triple-validation) are sound and worth adopting. The
   *ontologies* they produce are not reusable for us — wrong working group (SA2/SA5, not
   RAN2/CT1), retrieval-shaped, and shallow on the UE behavioral semantics that are our
   hard problem.

### 1.2 Landscape

| Work | What it is | What to borrow | Caveat |
|---|---|---|---|
| **Telco-RAG / Telco-oRAG** | RAG over 3GPP; **neural router over the 18 series (21–38)** with per-series summary embeddings | The series-numbering-as-top-level-taxonomy idea; per-series summaries as a cheap corpus-layer artifact | Series organize *publication*, not *concepts*; one UE procedure spans several series. Routing is a runtime trick (out of our scope) |
| **Dynamic KG + Explainable RAG** | Domain ontology aligned to **3GPP SA2**; **hybrid deterministic + LLM** triple extraction; triple-validation vs. existing knowledge; provenance via source citation | Validates our **Layer C (deterministic) vs Layer D (LLM)** split; the "validate new triples against the existing graph to curb hallucination" technique | Anchored to **SA2 (architecture/core)** — wrong WG for UE radio/NAS. Its own stated limits (informal-language coverage, release dynamics, validation difficulty) are real and **unsolved** |
| **SpecGraph-style typed KG** | Typed nodes (Procedure, Message, Property), typed edges, metadata storing **clause/table/figure provenance** | The typed-node + **provenance-metadata-on-every-node** pattern (our provenance spine) | Published schemas are thin; "Property" is a catch-all. Design our own type system; borrow the pattern |
| **TSpec-LLM** | Open dataset, **all 3GPP docs Rel-8→19**, ~535M words, preprocessed | A ready **corpus source** — saves scraping/parsing .docx ourselves | Built for LLM *comprehension eval*, not taxonomy; doesn't tell us if a taxonomy is "right". **Gated (CC-BY-NC-4.0 + HF login)** — the NC license matters if SAGE artifacts ever go commercial; the ungated `GSMA/3GPP` HF mirror (Rel-8→20, originals + markdown) is what D-021 actually uses |
| **TeleQnA** | ~10k telecom MCQs | A *starting* downstream eval | MCQ format; does not measure taxonomy coverage/correctness — we need our own eval |
| **TM Forum SID → OWL** | Mature telecom enterprise ontology, OWL-translated | Upper vocabulary for any network-side anchor | SID is **OSS/BSS + network-resource (SA5)** oriented — models functions/services/resources, not RRC procedures/timers/IEs. Largely orthogonal to UE |
| **Chat3GPP / TelcoAI / ORAN RAG bench** | More open 3GPP RAG pipelines; hybrid vector+graph retrieval benchmarks | Engineering patterns (chunking, hybrid retrieval evidence) | All retrieval-focused; KG is a means, not the artifact |
| **TelcoAgent** *(added 2026-07-16; arXiv 2606.19821, Jun 2026)* | Three-agent LLM pipeline that **auto-builds a 3GPP KG** from 13 RAN/performance specs (incl. TS 38.331), ontology-based schema, grounding KPM-forecast explainability | The closest new neighbor — aligner-stage idea + released KG covers TS 38.331 (comparison data for our RRC pilot); deep-read in §1.5 | KG serves forecast *explainability*, not a spec model; no provenance, no extraction validation, no UE-vs-network distinction, no multi-release modeling (§1.5). Confirms, not threatens, our thesis |
| **DeepSpecs** *(added 2026-07-16; arXiv 2511.01305)* | RAG for 5G spec QA enhanced with **structural/temporal metadata** databases; two new curated QA sets (573 practitioner + **350 evolution-focused** questions) | The **evolution-focused QA set** is a candidate eval for our D-011/D-012 change-tracking queries (partial answer to the unowned-eval-data flag); **CR-rationale mining** (§1.5) is worth adopting for D-012 | Still RAG-first; no taxonomy/ontology/KG; no UE scoping. **QA sets/code not publicly released** — "available upon email request" (§1.5) |

### 1.3 Borrowable ideas — pros / cons

- **Series numbering (21–38) as the top-level corpus taxonomy.** *Pro:* free, authoritative,
  already the de facto organization; cheap scope filter. *Con:* publication axis, not
  conceptual; coarse; a UE procedure crosses series. *Decision:* adopt as the **document/
  provenance spine** (Hierarchy A), not as the conceptual ontology.
- **Typed nodes + provenance metadata on every node** (SpecGraph-style). *Pro:* exactly our
  provenance design; traceable. *Con:* others' schemas are thin. *Decision:* adopt the
  pattern; design our own type system.
- **Hybrid deterministic + LLM extraction with triple-validation.** *Pro:* matches our
  Layer C/D split; validation curbs hallucination. *Con:* inherits unsolved limits
  (informal language, release dynamics, validation). *Decision:* adopt the architecture;
  treat their limitations as our risk list.
- **TSpec-LLM corpus + TeleQnA eval.** *Pro:* ready corpus + a starting eval. *Con:*
  comprehension-eval / MCQ, not taxonomy-coverage. *Decision:* candidate corpus source;
  build taxonomy-specific eval ourselves.
- **SID/OWL & SA2-aligned ontologies.** *Pro:* mature upper vocabulary. *Con:* wrong domain
  (network/core, not UE protocol). *Decision:* borrow sparingly for network-side anchors only.

### 1.4 Validation refresh (2026-07-16)

All external claims in this review were re-verified via adversarially-checked web research
(25 top claims verified, 0 refuted). Outcomes:

- **Headline findings 1–3 stand.** Two new papers appeared since the June review — TelcoAgent
  (Jun 2026) and DeepSpecs — both added to §1.2; both are still RAG/explainability-first with
  no UE-vs-network modeling and no multi-release evolution.
- **All eight prior-work citations check out** (papers exist, characterizations accurate); the
  Telco-oRAG wording in finding 2 was softened (absent, not explicitly disclaimed).
- **Spec versions moved on** (expected; the D-011/D-012 machinery's use case): TS 38.331 is at
  19.3.0 (2026-06-26); TS 24.229 is at 19.7.0 *and* has a first **Rel-20 version 20.0.0**
  (`24229-k00.zip`, 2026-06-29 — 'k' prefix confirmed; NORA's downloader already handles it).
- **Rel-19 is fully frozen** (functional freeze Sep 2025 TSG#109; code freeze Dec 2025
  TSG#110) — a stable v1 substrate. Rel-20 = 5G-Advanced + first 6G *studies*; first normative
  6G lands in Rel-21 (Stage-3 freeze Dec 2028, timeline approved 2026-06-10).
- **Spec-content spot-checks all correct** (5.3.3/T300, 5.3.5/T304, three RRC states,
  Need M/N/S/R codes, TS 24.229 = prose SIP/SDP Stage-3).

### 1.5 Deep-read: TelcoAgent & DeepSpecs (2026-07-16)

Full-text review of the two new papers, asking: *could we adopt TelcoAgent's pipeline for
KG construction on UE-relevant specs — what does it lack for our purpose?*

**TelcoAgent (arXiv 2606.19821) — what it actually does.** Three sequential LLM agents:
an **Extractor** (section-level chunks → subject–predicate–object triples, aimed at "KPM
relationships and causal chains"), an **Aligner** (normalizes entities onto a "canonical
3GPP ontology"), an **Evaluator** (LLM self-scores each triple q ∈ [0,1]; q < 0.9 triggers
re-alignment). Ingests 13 specs: TS 28.552/28.554/38.314, TS 38.211–215 + TR 38.901,
TS 38.300/38.321/38.322/38.331. The KG's purpose is grounding *explanations of
KPM-forecast degradations* — not modeling spec behavior.

**Why it doesn't serve our purpose as-is** — five load-bearing gaps, measured against
SAGE's requirements:

1. **No provenance/grounding.** Triples carry no link back to clauses (not even the
   section chunk is tracked). Fatal vs. our `KG ⊨ corpus` invariant (D-008/D-019) and
   NORA's need to cite spec text behind every assertion.
2. **No extraction validation.** No precision/recall, no ground truth, no human eval of
   the KG; quality control is the LLM grading its own output (Evaluator confidence).
   This is exactly the Layer-D validation problem — TelcoAgent doesn't solve it, it
   doesn't confront it. Our deterministic backbone + validation + review queue + gold
   seed (D-010) stays the more conservative, auditable answer.
3. **No UE-vs-network scoping** — no filter, no actor distinction (reconfirms headline
   finding 2 / D-001).
4. **No release/version modeling** — no 3GPP release is even mentioned; single timeless
   snapshot. No counterpart to D-011/D-012.
5. **Undocumented schema.** The "canonical 3GPP ontology" is never enumerated (no type
   counts, no origin); the extraction LLM is unnamed, so on-prem feasibility (our D-010
   constraint) can't be assessed. KG size and node/edge counts unreported.

Implementing it faithfully would produce an ungrounded, unversioned, unvalidated triple
soup — the failure mode SAGE's architecture is designed against. **Worth taking:**
(a) the **Aligner as a distinct stage** — an LLM pass canonicalizing surface forms onto
ontology entities could cut review-queue noise (constrained propose-only, human-confirmed,
per D-015); (b) their **released KG** (github.com/NextG-Wireless-Lab-NC-State/TelcoAgent)
covers **TS 38.331 — same spec as our RRC pilot** — diffing their 38.331 triples against
our pilot KG is a cheap external sanity check on what unvalidated extraction produces.

**DeepSpecs (arXiv 2511.01305) — the more useful paper, with a catch.** No KG; RAG over
three metadata databases, two of which map onto our D-012 gap: **ChangeDB**
(clause-aligned, line-level diffs between adjacent spec versions) and **TDocDB** (mines
approved Change Requests — summary of change, reasons, consequences of non-approval).
Our `derive()` tracks *what* changed across releases; **CR mining adds *why*** — adopt
for the cross-release work. The catch: the 573-question practitioner set and the
350-question CR-focused set (built from 997 approved Rel-17/18 CRs) are **not publicly
released** — code "available upon email request", no dataset URL — so the eval-data lead
requires contacting the authors. Also instructive: their best cross-reference-resolution
F1 is **0.28** (903 references) — evidence that our deterministic INVOKES extractor is
the right call over retrieval-based reference resolution.

---

## 2. Agreed taxonomy approach (D1–D4)

> **Status: agreed 2026-06-05.** These are working agreements for phase-0, not yet COMPACT
> decisions. Promote to `DECISIONS.md` (`D-XXX`) when we enter the requirements/architecture
> phases.

### Core claim: two orthogonal hierarchies, joined by provenance

Not one tree. Forcing the document structure and the domain structure into a single
hierarchy is a classic ontology mistake.

### D1 — Two hierarchies, joined by `DEFINED_IN`

**Hierarchy A — Document / provenance spine** (top-down, deterministic, from 3GPP's org):

```
3GPP
├─ TSG (RAN · SA · CT)              ← who writes it
│   └─ Working Group (RAN2, CT1…)   ← conceptual owner
└─ Series (21–38)                   ← publication axis
    └─ Specification (TS/TR ####)
        └─ Release (Rel-15…19)
            └─ Version
                └─ Clause (n.n.n)
                    └─ {ASN.1 block | Table | Figure | Prose ¶}
```

Where text *lives*. Cheap/reliable from 3GPP metadata. Every knowledge node points back here.

**Hierarchy B — Domain / conceptual taxonomy** (the UE ontology):

```
UE
└─ Protocol Stack
    └─ Stratum (Access Stratum | Non-Access Stratum)
        └─ Protocol Layer (PHY·MAC·RLC·PDCP·SDAP·RRC | NAS-MM·NAS-SM | IMS/SIP)
            └─ { Procedure · Message · InformationElement · Timer · State · Event · Condition · Capability }
```

Upper levels (down to Protocol Layer) are **small, stable, hand-curated**. Everything below
"Procedure" is **content-derived**. The hand-curated / extracted boundary sits at Procedure.

**The join:** B's leaf entities are `DEFINED_IN` A's clauses — the edge that makes everything
traceable and answers "which spec/release/clause says this?"

### D2 — B's upper skeleton: `UE → Stratum → Layer → {entity types}`

Hand-curated to Layer; extracted below. **v1 entity types** (open to extension):
Procedure, Message, InformationElement, Timer, State, Event, Condition, Capability.
*Open: do we add `Bearer`, `QoS Flow`, `Identity`, `Channel` as first-class types or model
them as IEs/properties? Revisit during RRC pilot.*

### D3 — UE-relevance filter (v1 corpus boundary)

| Series | UE relevance | Example specs |
|---|---|---|
| **38** (5G NR) | Core | 38.331 RRC, 38.321 MAC, 38.322 RLC, 38.323 PDCP, 38.300/304 |
| **24** (NAS, IMS — CT1) | Core | 24.501 5GS NAS, 24.301 EPS NAS, 24.229 IMS/SIP, 24.173 |
| **36** (LTE) | High | 36.331 RRC, 36.321/322/323 |
| **37** (multi-RAT) | Med | 37.340 MR-DC |
| **23** (architecture — SA2) | Partial | 23.501/502, 23.228 IMS (system context only) |
| **26 / 27 / 31 / 33** | Targeted | 26.114 MTSI, 27.007 AT, 31.102 USIM, 33.501 security |

### D4 — Build order

1. Build **Hierarchy A** (document spine) across the filtered corpus — cheap, deterministic;
   gives provenance + scoping.
2. Hand-curate **Hierarchy B**'s upper skeleton (UE → Stratum → Layer + entity-type set).
3. Populate **B**'s leaves **slice-by-slice** (pilots below).

---

## 3. Pilot plan

**Agreed order: RRC first, then IMS.**

- **Pilot 1 — RRC (TS 38.331).** Exercises every layer and has a **deterministic ASN.1
  anchor** (Layer C) to validate the fuzzy behavioral extraction (Layer D) against. Start
  with a single vertical procedure (e.g. RRC connection establishment) end-to-end. Goal:
  prove the entity/relationship model on the *easy* layer first.
- **Pilot 2 — IMS (TS 24.229 + 23.228, 26.114).** **Risk flagged:** IMS is **SIP-based —
  text, not ASN.1** — so the Layer C deterministic backbone mostly does **not** exist. IMS
  is dominated by prose procedures, SIP message structures, and tables (Layer D). It is a
  brutal stress test for the model (survives IMS → survives anything) and validates the
  approach where it's hardest. Doing it *second* lets us harden the method on RRC first.

---

## 4. Open questions / next steps

- ~~**Spec sourcing:** download from 3gpp.org vs. reuse TSpec-LLM's preprocessed corpus.~~
  *(resolved by D-021, noted 2026-07-16: corpus rebuilds from the ungated `GSMA/3GPP`
  HF mirror via NORA's downloader; TSpec-LLM is gated CC-BY-NC and not used.)*
- **Entity-type completeness (D2):** Bearer / QoS Flow / Identity / Channel — types or IEs?
- **Taxonomy correctness eval:** TeleQnA is insufficient; design a coverage/correctness check.
- **Store choice** (RDF/SKOS vs. property graph): still deferred to architecture; the
  two-hierarchy + provenance model above is store-agnostic so far.
- **Layer D validation:** the unsolved problem inherited from prior work — how to validate
  LLM-extracted behavioral triples without exhaustive human review.

---

## 5. Sources

- Telco-RAG — https://arxiv.org/pdf/2404.15939 · code https://github.com/netop-team/Telco-RAG
- Telco-oRAG — https://arxiv.org/html/2505.11856
- Dynamic KG + Explainable RAG (telecom) — https://arxiv.org/pdf/2602.17529
- CellularSpecSec-Bench — https://arxiv.org/pdf/2601.12716
- TSpec-LLM — https://arxiv.org/abs/2406.01768
- Chat3GPP — https://arxiv.org/html/2501.13954v1
- TelcoAI (agentic multimodal RAG) — https://arxiv.org/abs/2601.16984
- ORAN vector/graph/hybrid RAG benchmark — https://arxiv.org/pdf/2507.03608
- TM Forum SID → OWL (Semantic Arts) — https://www.semanticarts.com/telecom-frameworx-model-simplified-with-gist-full-article/
- TelcoAgent (3GPP KG for KPM-forecast explainability) — https://arxiv.org/abs/2606.19821 · released KG: https://github.com/NextG-Wireless-Lab-NC-State/TelcoAgent *(added 2026-07-16)*
- DeepSpecs (5G spec QA; evolution-focused QA set) — https://arxiv.org/abs/2511.01305 *(added 2026-07-16)*
- GSMA/3GPP raw-spec mirror (D-021 corpus source, Rel-8→20) — https://huggingface.co/datasets/GSMA/3GPP *(added 2026-07-16)*
