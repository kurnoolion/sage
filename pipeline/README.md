# SAGE extraction pipeline (D-010)

Builds the ontology/KG for a spec's **UE-relevant** clauses from its corpus store,
at scale, using a **deterministic-first** pass plus an **on-prem LLM** for
behavioural prose. One shared ontology across specs; per-spec config + gold seed.

```
per-release:  UE filter → deterministic extractors → LLM extractor → merge → validate → snapshot (+ review queue)
cross-release: derive(snapshots, aliases, review-decisions) → unified KG     ← future (D-012)
```

## Run

```bash
python3 -m pipeline.run --spec "TS 24.229" --version 19.6.0 --dry-run   # deterministic spine only
python3 -m pipeline.run --spec "TS 24.229" --version 19.6.0             # + LLM if endpoint configured
python3 -m pipeline.run --version 19.6.0 --limit 20                     # LLM over first 20 UE clauses
```

Outputs go to `pipeline/snapshots/<SPEC>-<VER>/` (gitignored — regenerable, carry
verbatim anchors): `snapshot.json` (KG, same shape as the pilot's `kg.json`),
`review-queue.json`, `ue-filter-report.json`.

## Wiring the on-prem model (stage 3)

Model-agnostic, **OpenAI-compatible** (stdlib only — no SDK). Configure via env:

```bash
export SAGE_LLM_BASE_URL=http://localhost:11434/v1      # Ollama
# or                       http://<gpu-host>:8000/v1    # vLLM
export SAGE_LLM_MODEL=qwen2.5:32b-instruct
export SAGE_LLM_API_KEY=…                               # optional (vLLM/OpenAI)
```

With no `SAGE_LLM_BASE_URL` (or `--dry-run`), stage 3 is a **no-op stub**: the
prompt is still built (inspectable) but no network call is made, so the
deterministic spine always runs. The model must return a JSON array of facts
(`{subject, subject_type, rel, object, object_type, modality, confidence, anchor}`);
the **anchor must be a verbatim clause span** so `KG ⊨ corpus` holds.

## Modules

| File | Stage / role |
|---|---|
| `ontology.py` | shared TBox (entity + relationship types, `subtype_of`); subtype-aware `domain_range_ok` |
| `ids.py` | namespaced ids `3gpp:<layer>/<type>/<name>` (D-013) |
| `config.py` | per-spec `SpecConfig` (corpus path, layer, UE-relevance hints) + registry |
| `corpus.py` | load a frozen corpus store; `haystack()` for anchor resolution |
| `ue_filter.py` | **stage 1** — select UE-side clauses (structural + actor-term fallback) + report |
| `extractors.py` | **stage 2** — deterministic: Procedures (titles), SIP vocab, INVOKES (cross-refs) |
| `llm.py` | **stage 3** — OpenAI-compatible client + few-shot prompt builder (stub-safe) |
| `records.py` | KG entity/relation builders (canonical shape + D-011 lifecycle/provenance) |
| `validate.py` | **stage 4** — `KG ⊨ ontology` (subtype-aware) + `KG ⊨ corpus` |
| `snapshot.py` | **stage 5** — write snapshot + review queue (low-confidence / warnings) |
| `run.py` | orchestrator / CLI |
| `gold/<SPEC>.json` | curated gold seed = few-shot examples **and** precision/recall eval set |

## Division of labour (D-010)

Human owns schema / gold examples / prompt / validation. The deterministic pass
lays a **high-precision entity backbone** (anchors); the on-prem model mines
**behavioural** edges (`EXCHANGES`, `STARTS`, `HAS_PRECONDITION`, …) over filtered
prose. Validation + review queue contain hallucination; nothing low-confidence is
silently merged.

## Status

Deterministic spine runs on TS 24.229 (169/2096 UE clauses → 149 entities /
30 relations, 0 errors / 0 warnings). LLM stage built + stubbed, pending an
endpoint. Known precision-tuning item: the title-based Procedure extractor
over-generates on parameter / "abnormal cases" clauses — refined by the LLM type
pass + review.
