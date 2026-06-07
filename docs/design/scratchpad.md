# Design scratch pad

**Status**: living working notes — NOT authoritative. We distill this into the formal design
doc later. Decided items live in `docs/compact/DECISIONS.md`; this captures reasoning, the
not-yet-formalized change-tracking/derivation model, open decisions, and risks.

**Scope of this pad (so far)**: multi-release modelling + change tracking + the derivation
pipeline shape. Established context (the 3 layers, ontology/KG/corpus split, concept scheme,
extraction approach) is in `DECISIONS.md` D-001…D-011 and `rrc-pilot/README.md` — not repeated
here except where change-tracking touches it.

---

## 0. Established context (pointers, already decided)

- 3 layers: **corpus** (verbatim, per-version), **ontology** (schema), **KG** (text-free
  instances + provenance). [D-003, D-004]
- KG indexes, doesn't re-encode; per-edge `modality`/`confidence`. [D-005]
- Extensible seed schema. [D-006]; store deferred [D-007]; validation invariants
  `KG ⊨ ontology`, `KG ⊨ corpus` [D-008].
- Extraction = curated gold seed + few-shot + on-prem local model; deterministic-first;
  validation guardrail; review queue. [D-010]
- Multi-release = shared identity + versioned assertions; `Release` first-class; lifecycle
  fields `observed_in`/`introduced_in`/`valid_until`/`supersedes`; provenance is a **per-version
  list**. [D-011]

---

## 1. Foundation — the two commitments everything rests on

**(a) Deterministic, semantic keys** (release-agnostic) so two releases' facts are recognized
as the same fact:
- **Entity key** = `type | canonical-name | layer`  (e.g. `Timer|T300|RRC`).
- **Relation key** = `from-key | predicate | to-key [| role]`. Identity-affecting only;
  `guard`/`direction`/`needCode`/value are **versioned attributes**, not part of the key.
- **Attribute-timeline key** = `(owner-key, attribute-name)`  (e.g. `(Timer|T300|RRC, value)`).
- **Assertion id** = content-derived (`owner|attr|valid_from`), so re-derivation is stable.

> If ids were insertion-order/random, none of the diff/merge/idempotency works. Deterministic
> content-derived ids are the linchpin.

**(b) Snapshots are the source of truth; the unified KG is a derived projection** (event-sourcing).
- Each extraction run emits an **immutable per-`(spec, version)` snapshot**: sets of entity-keys,
  relation-keys, attribute observations `(key → value)`, each with that version's provenance.
- A **pure `derive()`** folds *all* snapshots + the alias map + review decisions → the unified KG
  (with lifecycle + value-assertions). The unified KG is **never hand-mutated**; it's recomputed.
- This single choice gives: order-independent diffs, idempotent re-ingest, minimal churn.

```
extract(version) ─► snapshot[(spec,version)]  (immutable, append-only)
                         │
   alias-map ──────────► derive()  ─►  unified KG (lifecycle + assertions, deterministic ids)
   review-decisions ────►
```

---

## 2. Computing `introduced_in` / `removed_in` / `supersedes`

`derive()` walks releases ascending, reconciling by key.

**Presence lifecycle (entities & relations):**
- key in snapshot N, unseen before → `introduced_in = N`, `observed_in = [N]`.
- key in N and earlier → append N to `observed_in` (no lifecycle change).
- key seen through N-1, **absent** in N → `removed_in = N`, `valid_until = N-1`.

**Value lifecycle (`supersedes`) — per attribute timeline `(owner, attr)` with value `v_N`:**
- no prior open assertion → open (`value=v_N, valid_from=N`).
- `v_N == current open value` → extend (append N to its `observed_in`).
- `v_N != current value` → **close** current (`valid_until = N-1`) + **open** new
  (`value=v_N, valid_from=N, supersedes=<prev id>`).

`supersedes` is set exactly at a value change. A→B→A yields a 3-link chain (the second A is a new
assertion) — correct, it changed twice.

**Caveats to bake in (honesty):**
- **`introduced_in` at the corpus floor is a lower bound.** Earliest ingested release = Rel-15 ⇒
  things there get `introduced_in = Rel-15` but we can't know about Rel-14. Flag
  `introduced_at_floor: true`; don't assert false precision.
- **Absence ≠ removal** (could be extraction miss). Prefer **explicit deletion signals** —
  3GPP "Void" clauses, change marks — over inferring from absence; low-confidence disappearance →
  **review item**, not auto `removed_in`.

---

## 3. Value-assertions — keying & merging (SCD-2)

- Timeline keyed `(owner-key, attr-name)`; individual assertions are **segments** of it.
- `derive()` collects per-release observations `release → value`, sorts by release, **coalesces
  consecutive equal values into one segment** (`valid_from..valid_until`). Coalescing *is* the
  merge.
- Each segment carries its **own per-version provenance list** (releases/clauses asserting that
  value).
- Needs a **value-normalization** fn per attribute type (ASN.1 enum compared as a *set*; timer
  compared numerically) — else cosmetic reordering yields false "changes". Real, testable
  component.
- Same machinery for **relation attributes** (changed `guard` = value-assertion on the relation,
  not a new relation).

---

## 4. Churn-free re-ingestion of corrected versions

3GPP ships many versions per release (v19.1.0 → v19.2.0 corrections).
- **Re-ingest = replace that one `(spec, version)` snapshot** (idempotent by key) → **re-derive**.
- **Content-derived ids + deterministically sorted output** ⇒ unchanged facts serialize
  byte-identically ⇒ git/DB diff shows *only* what the correction changed. (Random ids would
  reshuffle everything → false churn. This is *why* ids are deterministic.)
- **Representative version per release**: KG keeps one version per release as the provenance
  representative (latest within the release); a correction updates that entry
  (`19.1.0 → 19.2.0`) + any changed facts. Sub-release churn doesn't leak into release-level
  lifecycle.
- Net: re-running the whole pipeline is safe and near-noiselessly idempotent.

---

## 5. Review queue — renames & ambiguous merges

Presence diff naively reads a **rename** as `remove(old)+introduce(new)` → severs identity/history.
So `derive()` runs a **rename/merge detector** before finalizing.

**Match a disappeared key (release N) against keys new in N, using signals:**
- label similarity (edit distance), same type + layer;
- **structural overlap** — shares most incident relations (renamed procedure keeps its edges) —
  usually strongest;
- same/adjacent clause; explicit spec signals (documented renames; `-rNN` suffix pattern).

**Never auto-merge identity.** Above a similarity floor → **review item**:
> "Possible rename: `oldKey` (gone Rel-N) ↔ `newKey` (new Rel-N) — sim 0.9, 7/8 shared neighbours.
> [confirm-rename / keep-separate / split / merge]"

- Human (domain-validator surface, D-010) decides → written to a **durable alias/decision file**
  that feeds the *next* `derive()` (recorded once; re-derivation never re-asks).
- On confirm-rename: old+new collapse to one identity; `introduced_in` inherits from old; node
  gets `renamed_in: Rel-N`, `aka: [oldName]`.
- Same queue absorbs: **value conflicts** (same key, different values in one release),
  **splits/merges**, and **low-confidence LLM triples** that pass schema but were model-flagged.

---

## 6. Implied pipeline architecture

```
per-release:  UE-relevance filter → deterministic extractors → LLM extractor (few-shot)
              → validate (KG ⊨ ontology, KG ⊨ corpus) → snapshot[(spec,version)]
cross-release: derive(snapshots, alias-map, review-decisions) → unified KG
              → emit review items for unresolved identity/conflict/low-confidence
outputs: kg.json (deterministic, sorted) + review/*.md + views
```
- Deterministic + idempotent end-to-end; LLM only ever sees one release's text.
- Lifecycle/history computed by `derive()`, never authored by the LLM.

---

## 7. Open decisions to lock (candidates)

- **D-012 (proposed): change-tracking / derivation model** — snapshots-as-truth + pure `derive()`
  + content-derived ids + review queue (this whole pad). Record when we start the pipeline.
- **`-rNN` suffix handling** — lean: keep the suffixed name as the canonical id (genuinely distinct
  ASN.1 fields) but read the suffix as an `introduced_in` signal; only collapse `foo`↔`foo-r16`
  via review/alias. Decide explicitly.
- **Value normalization** per attribute type — define the canonical-form functions (enum=set, etc.).
- **Removal-detection policy** — explicit Void/change-mark vs. absence; confidence threshold → review.
- **Representative-version policy** — latest-in-release for provenance; confirm.
- **`introduced_at_floor` flag** — adopt to mark lower-bound introductions.
- **Rename-similarity floor** + which signals weighted how.

## 8. Risks / hard parts

- **Name canonicalization** (suffixes, abbreviations, synonyms) — main source of bad merges → review.
- **Absence-as-removal** unreliable → rely on explicit signals + confidence.
- **Value normalization** sloppiness → false change history.
- **Entity resolution at scale** — structural-overlap matching across thousands of nodes needs to
  be efficient.
- **`introduced_in` is only a lower bound** until the earliest relevant release is ingested.

## 9. Worked examples

**T300 value, two changes:**
```
A1 value=v1 valid Rel-15..Rel-16  (supersedes —)   prov: [Rel-15 §x, Rel-16 §y]
A2 value=v2 valid Rel-17..Rel-18  (supersedes A1)   prov: [Rel-17 §z, Rel-18 §z]
A3 value=v3 valid Rel-19..(open)  (supersedes A2)   prov: [Rel-19 §5.3.x]
```
"value at Rel-17" = segment covering Rel-17 (A2); "current" = A3; "history" = A1→A2→A3.

**Clause renumbering (same fact):**
```
P_setup --STARTS--> T300
  provenance: [ {Rel-17, v17, clause 5.3.3.4, "start timer T300"},
                {Rel-19, v19, clause 5.3.3.2, "start timer T300"} ]   # number changed, fact didn't
```

**Rename (review-gated):** `foo` gone in Rel-18, `bar` new in Rel-18, 0.9 similarity, 7/8 shared
neighbours → review → confirm → unified node `bar` with `aka:[foo]`, `renamed_in: Rel-18`,
`introduced_in` inherited from `foo`.
