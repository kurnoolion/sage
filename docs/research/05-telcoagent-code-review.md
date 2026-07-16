# Research 05: TelcoAgent Code Review — Honest Comparison with the SAGE Pipeline

**Status**: Complete (2026-07-16). Deep-read of TelcoAgent's released KG-construction code
(MIT, `github.com/NextG-Wireless-Lab-NC-State/TelcoAgent`) against SAGE's D-010 pipeline,
component by component, to decide what is worth adopting.
**Inputs**: full source of `telcoagent/kg_construction/` (pipeline, extractor, aligner,
evaluator, prompts, tools, kg_builder, schema — ~2.5k lines), the shipped
`data/enriched_kg.json`, and SAGE `pipeline/` modules.
**Companion**: doc 01 §1.5 (paper-level review — two claims corrected here, see §0).

---

## 0. Corrections to the paper-level review (doc 01 §1.5)

Reading the code corrected three claims made from the paper alone:

1. **Provenance exists at clause level.** Every triple carries `source_spec` +
   `source_clause` (+ optional LLM-emitted `fine_clause`), and KG nodes accumulate
   provenance lists (`spec:clause` strings). What is missing is **span-level anchoring**:
   the per-triple `raw_text` is literally `chunk.body[:200]` — the first 200 characters
   of the chunk regardless of where the fact appeared — and nothing ever verifies that
   the cited text supports the triple. So: provenance recorded, grounding unverified.
2. **The pipeline is much richer than the paper describes.** It is an implementation of
   the **KARMA** multi-agent KG-enrichment framework (arXiv 2502.06472): Reader
   relevance filter (δ-threshold, disabled by default), LLM Summarizer for long clauses,
   ReAct tool-using Extractor/Aligner/Evaluator, optional embedding alignment (SAA),
   LLM conflict-resolution debate (CRA), and a bounded (1-iteration) feedback loop.
   The release is the **full MIT-licensed pipeline**, not just results.
3. **The shipped KG kills the RRC-comparison idea.** `enriched_kg.json` holds only
   **487 nodes / 439 edges**, with edges from just three specs (TS 28.552: 325,
   TS 28.554: 53, TS 38.214: 43, plus 18 unattributed). **TS 38.331 contributed zero
   edges** despite being an input — so diffing their 38.331 triples against our RRC
   pilot (previously a STATUS Next item) is impossible; there is nothing to diff.
   Default extraction model: `gpt-4o-mini` (cloud; on-prem feasibility unaddressed).

## 1. Their pipeline, as actually built

```
PDF → parse (SectionChunk) → [Reader δ-filter, off] → [Summarizer if >6000 chars]
    → Extractor (ReAct, ontology tools, ≤5 steps/chunk)
    → Aligner (LLM batch map → ontology short_names; optional SBERT/OpenAI embeddings;
               hard-coded pin of the 7 task KPIs; CRA conflict debate)
    → Evaluator (LLM 3-signal self-score C/Cl/R; mean ≥ Θ=0.9 → approved;
                 flag_for_reprocessing → one feedback pass)
    → KG builder (NetworkX; dedup by (s,p,o) hash; unknown predicate → generic edge)
    → JSON (+ optional Neo4j push)
```

Per-stage JSON caches enable resume and Θ-sweeps (scores are threshold-agnostic;
approval is recomputed in Python). 15s inter-call delay by default (free-tier APIs).

## 2. Component-by-component comparison

### 2.1 Corpus / parsing
| | TelcoAgent | SAGE |
|---|---|---|
| Source | ad-hoc PDF parse per run | frozen corpus store from HF `.docx` (D-021) |
| Cleanup | regex de-hyphenation/whitespace | build-time normalization; verbatim store |
| Reproducibility | re-parse each run, lossy PDFs | versioned `clauses.json`, diff-able (D-012) |

**Verdict: keep ours.** Nothing to take.

### 2.2 Scope filtering
Theirs: LLM "Reader" scores each section 0–1 vs δ — **shipped disabled** (δ=0),
fail-open. Ours: deterministic UE filter + kept/dropped report.
*Pro theirs*: no per-spec config. *Con theirs*: one LLM call/section for triage;
unauditable; they don't trust it themselves.
**Verdict: keep ours.** Filter decisions must be reviewable.

### 2.3 Long-clause handling — sharpest philosophical split
Theirs: clauses > 6000 chars are **LLM-summarized** before extraction (silent
truncation on failure) — extraction then runs on *paraphrased* text, destroying any
verbatim grounding before it begins, and summarization can silently drop facts.
Ours: deterministic paragraph-boundary chunking into verbatim substrings (D-018);
anchors resolve against the full clause.
**Verdict: ours is categorically right for a grounded KG.** (Same 6000-char threshold
on both sides, amusingly.)

### 2.4 Extraction
Theirs: ReAct agent (≤5 tool steps/chunk) with `search_ontology` / `get_kpi_details`;
prompt mandates entity-pass-then-relation-pass and a **closed 5-relation vocabulary**
(`INCREASES/DECREASES/DETERMINES/LIMITS/CAUSES`) + per-triple `relation_prob`.
Ours: single-shot few-shot prompt (ontology card + gold examples), mandatory verbatim
anchor, modality, confidence.

*Pro theirs*: tool-grounded canonicalization during extraction shrinks alignment work;
entity-first decomposition is sound prompt engineering.
*Con theirs*: ~5 LLM round-trips/chunk (slow, cloud-priced); needs reliable
function-calling — the weak spot of local models; and **empirically the mandated
vocabulary was not obeyed**: the shipped KG's top relations are free-form
(`uses_counter`, `defined_as`, `valid_for`, `depends_on`, `unit`, `description`, …),
only 5 edges use canonical `INCREASES`, and **345/487 nodes (71%) are the catch-all
`Entity` type**. The builder's "unknown predicate → generic edge" fallback *absorbs*
schema violations instead of rejecting them.
*Con ours (honest)*: single-shot prompting makes the model guess canonical names blind;
misses land in the review queue — real friction a tool-loop would reduce. But our
validator hard-errors on undeclared types, so their erosion mode cannot happen.

**Verdict: keep our architecture; take the entity-pass-then-relation-pass prompt
instruction (free, A/B-testable via `pipeline.compare`).** Revisit constrained
tool-loops only with `llm_debug` evidence that our local model's function-calling
is reliable.

### 2.5 Alignment / canonicalization — their most valuable component for us
Theirs: dedicated Aligner — LLM maps batches of 20 surface names to ontology
`short_name`s (or proposes normalized new names); optional **embedding
nearest-neighbor** (SBERT local or OpenAI) with cosine distance recorded per entity;
failed alignments kept as `NEW_TYPE` @ 0.3, not dropped. Plus a hard-coded override
(`_enforce_core_kpi_alignment`) that forcibly pins their 7 task KPIs and bumps
confidence to 0.95 — **the code's own testimony that the LLM aligner alone was not
reliable enough for the entities they actually cared about**.
Ours: nothing equivalent — deterministic ids from surface names; terminology variants
become distinct entities or review-queue noise.

**Verdict: this is SAGE's real gap. Take the aligner stage — embedding-first, not
LLM-first**: local SBERT nearest-neighbor over ontology/KG entity names emitting
`(surface_form → canonical_id, distance)` as **propose-only review-queue suggestions**
(D-015: human confirms; extractor conforms). The same machinery doubles as the
**alias-table builder D-012 `derive()` needs** for cross-release entity matching.
An LLM pass can be a second opinion later; it is not the backbone.

### 2.6 Validation — the deepest divide
Theirs: LLM self-scores each triple on confidence/clarity/relevance; mean ≥ Θ=0.9 →
approved. **The Evaluator never sees the source text** — only the triple JSON +
ontology tools — so "factual correctness" is scored without evidence. The mean lets a
dubious triple pass (C=0.7, Cl=1.0, R=1.0 → 0.9 ✓). Only mechanical check: formula
token-overlap (any shared token passes).
Ours: mechanical `KG ⊨ ontology` (hard errors, subtype-aware domain/range) +
`KG ⊨ corpus` (anchor must resolve verbatim, D-008/D-019) + review queue.

**Verdict: keep ours entirely.** Their evaluator is the LLM-grading-its-own-homework
pattern, and the shipped KG shows it did not even keep the schema clean. One pattern
worth keeping: **Θ-agnostic scoring** — store raw signals, apply thresholds at read
time so re-filtering never re-runs the expensive pass (we already store per-fact
confidence; this endorses keeping review-queue thresholds a read-time decision).

### 2.7 Conflict resolution (KARMA CRA) — a real gap in SAGE
Theirs: group triples by (aligned subject, predicate); where objects differ, an LLM
debate rules agree/contradict and **drops the loser** (by `relation_prob`, tie-broken
by clause depth; capped at top-10/group).
Ours: nothing — two LLM facts asserting different objects for the same (subject,
relation) both merge silently if individually valid.

**Verdict: take the deterministic *grouping*, not the LLM debate and not the drop.**
Flag same-(subject, rel), different-object groups into the review queue. Pure Python,
immediately useful for D-020 (two-model disagreements are exactly these groups) and
for D-012 (a cross-release object change is *signal* — auto-dropping the loser, as they
do, would be wrong for us).

### 2.8 Feedback loop
Theirs: evaluator flags → one bounded re-extract/re-align pass. Ours: review queue →
human. **Verdict: narrow adoption** — auto-retry a clause once when its LLM output was
entirely unparseable (today we only log it). Low priority.

### 2.9 Ops
Theirs: per-stage JSON caches (resume + cheap Θ sweeps), parallel evaluator
(8 threads), LiteLLM fallback chains, session cost tracking, 15s rate-limit delays.
Ours: checkpoint snapshots, progress/ETA, stable error codes (D-017), per-label
parallel runs (D-020). **Verdict: comparable maturity.** Their finer cache granularity
(raw extraction cached separately from scoring) is what makes sweeps cheap — remember
it when building eval sweeps; no retrofit now.

## 3. Adoption decisions

Ranked by value-for-effort:

1. **Conflict grouping → review queue** (from CRA, de-LLM'd): flag same-(subject, rel)
   different-object fact groups. Small pure-Python change; unblocks sharper D-020
   comparison and feeds D-012.
2. **Embedding alias suggester** (the Aligner, embedding-first): local SBERT
   nearest-neighbor, propose-only suggestions with distances, **with KARMA's ρ
   cutoff** (above the distance threshold → propose *new entity*, not a merge — §5.3);
   doubles as the D-012 alias table builder.
3. **Entity-pass-then-relation-pass prompt instruction**: free; A/B-test with
   `pipeline.compare`.
4. **Bounded auto-retry on unparseable clause output**: low priority.

**Explicitly rejected**: LLM summarization of long clauses (destroys anchoring); LLM
self-scored quality gates (evidence-free, empirically leaky); LLM relevance filtering
(shipped disabled by its own authors); ReAct tool-loop extraction on-prem (unproven
local function-calling — revisit with `llm_debug` evidence); their KG as RRC
comparison data (no 38.331 edges exist).

## 4. The transferable lesson

**A prompt-mandated schema without a hard validator behind it erodes.** Their closed
5-relation vocabulary became ~20 free-form predicates; 71% of nodes fell into an
untyped catch-all — because the builder absorbed violations instead of rejecting them.
This is direct empirical support for SAGE's D-008 hard-validation design and for
D-015's "extractor conforms, humans extend" division: schema discipline must live in
a validator, not in a prompt.

## 5. KARMA itself — review of the upstream framework (added 2026-07-16)

TelcoAgent's pipeline is an implementation of **KARMA** (arXiv 2502.06472, NeurIPS 2025
spotlight; Peking U / Georgia Tech / Tsinghua) — nine collaborative agents enriching a
biomedical KG from 1,200 PubMed articles: Ingestion → Reader (relevance δ) → Summarizer
→ Entity Extraction + embedding normalization (`ê = argmin_v d(φ(e), ψ(v))`, flagged
*new* if distance > ρ) → Relation Extraction (`p(r|ê_i, ê_j) ≥ θ_r`) → Schema Alignment
→ Conflict Resolution (LLM debate) → Evaluator (3 signals C/Cl/R, sigmoid-weighted,
mean ≥ Θ). Findings that matter for SAGE:

1. **The LLM-vs-human correctness gap is quantified.** KARMA reports **83.1%
   LLM-verified correctness** (hold-out DeepSeek-v3 judge) against **0.625 human-expert
   scores** on the same output — a ~21-point gap between what an LLM judge approves and
   what domain experts accept. This is the cleanest published number behind our
   rejection of LLM self-scored quality gates and behind the Layer-D validation flag
   (STATUS): LLM-judged quality systematically overstates expert-judged quality. Their
   own limitations concede "domain experts must ultimately verify critical claims."
2. **TelcoAgent diverged from KARMA where it mattered most.** KARMA's CRA, on a
   Contradict verdict, "discards **or queues for manual expert review**, depending on
   the system's confidence" — the review-queue path is in the original design.
   TelcoAgent auto-drops the loser. Our adoption (§3 item 1: grouping → review queue,
   never auto-drop) is *more* faithful to KARMA than TelcoAgent is. KARMA's ablation
   makes CRA the biggest measured quality lever (~9.7% correctness drop without it;
   conflict ratios 0.132–0.238 — 13–24% of extracted edges removed as contradictory),
   supporting conflict grouping's #1 rank in §3.
3. **Take the ρ threshold.** KARMA's entity normalization flags an entity as *new*
   when embedding distance exceeds ρ, instead of force-mapping to the nearest
   neighbor. TelcoAgent's SAA has no such cutoff. Our alias suggester (§3 item 2)
   should include it: suggestions above the distance cutoff propose a *new entity*,
   not a merge.
4. **The grounding gap is inherited, not a TelcoAgent shortcut.** KARMA stores no
   provenance and never verifies triples against source passages; extraction runs on
   Summarizer output (paraphrase), same as TelcoAgent. The whole framework lineage
   lacks what `KG ⊨ corpus` provides. Also no benchmark against gold-standard IE
   datasets — evaluation is LLM-metric-first by their own admission.
5. **No code release from KARMA** — TelcoAgent is the accessible implementation (and
   the only telecom one), which is why reviewing its code (§2) was the right proxy.

*Caveat: reviewed via fetched full text, not a line-by-line PDF read; formulas and
numbers are quoted from the paper's text.*

## 6. Sources

- TelcoAgent repo (MIT) — https://github.com/NextG-Wireless-Lab-NC-State/TelcoAgent
  (cloned + reviewed 2026-07-16; 4 commits; `data/enriched_kg.json` sha256-locked)
- TelcoAgent paper — https://arxiv.org/abs/2606.19821
- KARMA (the framework the code implements; reviewed in §5) — https://arxiv.org/abs/2502.06472
  *(NeurIPS 2025 spotlight; biomedical; no code release)*
- SAGE counterparts: `pipeline/llm.py` (D-018 chunking, anchor contract),
  `pipeline/validate.py` (D-008/D-019), `pipeline/ue_filter.py`,
  `pipeline/extractors.py`, `pipeline/run.py`, `pipeline/README.md`
