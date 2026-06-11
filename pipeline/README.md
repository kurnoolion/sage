# SAGE extraction pipeline (D-010)

Builds the ontology/KG for a spec's **UE-relevant** clauses from its corpus store,
at scale, using a **deterministic-first** pass plus an **on-prem LLM** for
behavioural prose. One shared ontology across specs; per-spec config + gold seed.

```
per-release:  UE filter → deterministic extractors → LLM extractor → merge → validate → snapshot (+ review queue)
cross-release: derive(snapshots, aliases, review-decisions) → unified KG     ← future (D-012)
```

## Corpus (gitignored — rebuild it first)

The corpus store (`corpus/store/<spec>-<ver>/clauses.json`) is **gitignored** (3GPP
copyright), so a fresh `git clone`/`pull` has the code but no corpus and the
pipeline errors with *"No such file or directory: …/clauses.json"*. Rebuild it
from the public source (reuses NORA's downloader; LibreOffice needed only for
specs served as legacy `.doc`, e.g. TS 24.229):

```bash
python3 corpus/fetch_spec.py "TS 24.229" 19.6.0 Rel-19   # one spec, exact version
python3 corpus/fetch_spec.py --all                       # every spec SAGE uses
# NORA elsewhere? --nora-root <path> or export SAGE_NORA_ROOT=<path>
```

## Run

```bash
python3 -m pipeline.run --spec "TS 24.229" --version 19.6.0 --dry-run   # deterministic spine only
python3 -m pipeline.run --spec "TS 24.229" --version 19.6.0             # + LLM if endpoint configured
python3 -m pipeline.run --version 19.6.0 --limit 20                     # LLM over first 20 UE clauses
```

### Where snapshots are stored

Everything is written under **`pipeline/snapshots/`**, one directory per spec+version
(name = spec with spaces/dots removed, `-`, version), with an optional `<label>/`
sub-directory for parallel runs (`--label`):

```
pipeline/snapshots/
  TS24229-19.6.0/              # <SPEC>-<VER>; a label-less run
    snapshot.json             # the KG: entities + relations + validation (same shape as the pilot's kg.json)
    review-queue.json         # ambiguous / low-confidence items + validation warnings
    ue-filter-report.json     # what the UE filter kept / dropped
    ontology.json             # TBox exported for the viewer  (written by `pipeline.viz`)
    kg-view.html              # rendered graph                (written by `pipeline.viz`)
    compare.json              # cross-run diff                (written by `pipeline.compare`)
  TS24229-19.6.0/qwen/        # a labeled parallel run (snapshot.json, review-queue.json, …)
  TS24229-19.6.0/llama/
```

The path comes from `snapshot.dir_for()` (the single source of truth, shared by
run/viz/compare) and is anchored to the repo root, so it's the same regardless of
the working directory you launch from.

**Gitignored** (`.gitignore`: `pipeline/snapshots/`) — the files embed verbatim
corpus prose (3GPP copyright) and are regenerable, so they live only on the machine
that ran the pipeline and do **not** travel with `git pull`.

## View the snapshot

```bash
python3 -m pipeline.viz --spec "TS 24.229" --version 19.6.0
```

Exports the shared ontology to JSON (so SIP types get colours/legend) and renders
the snapshot through the generic viewer (`rrc-pilot/viz/build_kg_view.py`) into
`pipeline/snapshots/<SPEC>-<VER>/kg-view.html` (gitignored — embeds prose). Open
via `file://`. The viewer is data-driven: node colours from the ontology, focus
buttons from `procedure_ctx`, gold corpus-clause nodes with the verbatim prose and
anchor highlights, and "new since last view" rings. The same viewer renders the
RRC pilot with no args. Add `--label <name>` to view a specific parallel run.

## Run several LLMs in parallel and compare (D-020)

To evaluate two models on the same corpus, give each run its own `--label` (which
namespaces its snapshot dir, so concurrent processes don't collide) and its own
model via `--llm-model` / `--llm-base-url` / `--llm-api-key` (these override the
`SAGE_LLM_*` env for that run). Launch them as separate processes:

```bash
python3 -m pipeline.run --version 19.6.0 --label qwen  --llm-model qwen2.5:32b-instruct \
  --llm-base-url http://gpu1:8000/v1 > /tmp/qwen.log 2>&1 &
python3 -m pipeline.run --version 19.6.0 --label llama --llm-model llama3.1:70b-instruct \
  --llm-base-url http://gpu2:8000/v1 > /tmp/llama.log 2>&1 &
wait
python3 -m pipeline.compare --version 19.6.0 qwen llama
```

Snapshots land in `pipeline/snapshots/<SPEC>-<VER>/<label>/`. `compare` reports
per-label counts and, for each pair, the entity / relation / **LLM-fact** overlap
by id (Jaccard = how much the models agree on what they extracted), prints sample
divergent facts, and writes `compare.json`. View either run with
`python3 -m pipeline.viz --version 19.6.0 --label qwen`. Runs are fully isolated
(separate processes, read-only corpus, per-label output) — if both models share
one GPU box they'll contend for it, so true parallelism wants two endpoints.

## Wiring the on-prem model (stage 3)

Model-agnostic, **OpenAI-compatible** (stdlib only — no SDK). Configure via env:

```bash
export SAGE_LLM_BASE_URL=http://localhost:11434/v1      # Ollama
# or                       http://<gpu-host>:8000/v1    # vLLM
export SAGE_LLM_MODEL=qwen2.5:32b-instruct
export SAGE_LLM_API_KEY=…                               # optional (vLLM/OpenAI)
export SAGE_LLM_TIMEOUT=300                             # per-request seconds (default 300)
export SAGE_LLM_MAX_CLAUSE_CHARS=6000                  # split longer clauses into chunks (0=off)
```

Long clauses are split into **paragraph-boundary chunks** of ≤ `SAGE_LLM_MAX_CLAUSE_CHARS`
(default 6000) so a slow local model sees several short prompts instead of one
huge one (D-018). Splitting is deterministic (the corpus stores paragraphs
newline-separated) and each chunk is a verbatim substring, so anchors still
resolve against the full clause. Facts from all chunks merge by id; lower the
limit for more, smaller calls. Per-chunk calls log as `clause#i/n`.

### Debugging the endpoint (do this before a long run)

```bash
python3 -m pipeline.llm_debug --probe http://<gpu-host>:8000   # what API does it speak?
python3 -m pipeline.llm_debug --check                          # send one ping, report latency
python3 -m pipeline.llm_debug --clause 5.1.1.1 --version 19.6.0 # exact prompt sent + raw response + parsed facts
python3 -m pipeline.llm_debug --clause 5.1.1.1 --no-call        # just show the prompt (no endpoint needed)
python3 -m pipeline.run --version 19.6.0 --limit 3 -v          # 3 clauses, DEBUG logging
```

`--check` and `--clause` take the same `--llm-base-url` / `--llm-model` /
`--llm-api-key` overrides as `pipeline.run` (they win over `SAGE_LLM_*` env) —
useful when probing two models side by side without re-exporting.

`--clause` is how you see exactly *what was sent and what came back* for one
clause. It dumps corpus prose, so it is a local operator diagnostic — don't paste
it into a cross-boundary report (`--out FILE` writes it to disk; gitignore that).

### Watching progress mid-run

The run logs each clause as it goes (`[i/n] clause <key>`), plus a cumulative
**progress line** every `--progress-every` clauses (default 25) — clauses done,
facts so far, elapsed, and ETA:

```
  progress: 50/165 clauses (30%), 137 LLM facts so far (pre-merge), 6m12s elapsed, ~14m remaining
```

To inspect the **partial graph** while it builds, pass `--checkpoint-every N`: the
snapshot is rewritten every N clauses, so you can open it in the viewer mid-run
(`python3 -m pipeline.viz …`). The final snapshot is always written regardless.

```bash
python3 -m pipeline.run --version 17.12.0 --progress-every 10 --checkpoint-every 25 -v \
  2>&1 | tee /tmp/sage-run.log          # follow elsewhere with: tail -f /tmp/sage-run.log
```

The run also logs per-call latency / tokens-per-second, so a hang or timeout names the exact clause. Failures
carry a **stable error code + hint** (D-017): a timeout aborts with `[LLM-E001] LLM
timeout after Ns (limit Ns) on clause <key> | hint: raise SAGE_LLM_TIMEOUT …`
(`LLM-E002` HTTP, `LLM-E003` network, `LLM-E004` bad shape). Run logging defaults
to INFO; `-v` adds DEBUG (request shapes, parsed-fact counts). Logs carry only
clause ids + char/token counts — never corpus prose — and API keys are never logged.

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
| `config.py` | version-independent per-spec `SpecConfig` template (layer, UE-relevance hints); `get(spec, version)` derives the store path so any fetched version works |
| `corpus.py` | load a frozen corpus store; `haystack()` for anchor resolution |
| `ue_filter.py` | **stage 1** — select UE-side clauses (structural + actor-term fallback) + report |
| `extractors.py` | **stage 2** — deterministic: Procedures (titles), SIP vocab, INVOKES (cross-refs) |
| `llm.py` | **stage 3** — OpenAI-compatible client + few-shot prompt builder (stub-safe); per-call timing/token logging + timeout/error surfacing |
| `llm_debug.py` | endpoint probe (`--probe`) + configured-LLM ping (`--check`) for diagnosing hangs/timeouts |
| `compare.py` | diff snapshots across run labels (entity/relation/LLM-fact overlap, Jaccard) for multi-LLM eval |
| `error_codes.py` | stable `{MODULE}-{SEVERITY}{NUMBER}` codes + `PipelineError` (D-017; NORA D-012a convention) |
| `records.py` | KG entity/relation builders (canonical shape + D-011 lifecycle/provenance) |
| `validate.py` | **stage 4** — `KG ⊨ ontology` (subtype-aware) + `KG ⊨ corpus` |
| `snapshot.py` | **stage 5** — write snapshot + review queue (low-confidence / warnings) |
| `run.py` | orchestrator / CLI |
| `viz.py` | export shared ontology → JSON + render the snapshot via the generic viewer |
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
endpoint. Procedure anchors whose titles look structural (parameters / "as a
security mechanism" / "- general" / "abnormal cases") are kept but **demoted to
`confidence=med` and routed to `review-queue.json`** (currently 16) rather than
presented as solid facts — precise re-typing is the LLM/review's job
(D-010/D-015), not a title regex.
