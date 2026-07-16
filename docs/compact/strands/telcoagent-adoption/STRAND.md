# telcoagent-adoption

**Status:** in-flight
**Opened:** 2026-07-16
**Landed:**
**Assignees:** kurnoolion
**Target modules:** pipeline (run/llm/extractors/config/compare + new align, eval_gold), corpus (38.331 fetch), rrc-pilot (read-only as gold)
**Active phase:**

## Summary

Adopt the TelcoAgent/KARMA features selected in research doc 05 §3+§5 into the D-010
pipeline — conflict grouping → review queue, embedding-first alias suggester with ρ
cutoff (endpoint-primary, difflib fallback), entity-pass-then-relation-pass prompt,
bounded retry on unparseable output — then enable TS 38.331 in the pipeline
(SpecConfig, per-spec vocab, gold seed from the hand-built pilot) and rebuild the RRC
pilot clauses (5.3.3/5.3.5, v19.2.0) to measure pipeline precision/recall against the
hand-built KG, including our own KARMA-style LLM-vs-expert gap number for the Layer-D
flag.

## Notes

Plan agreed 2026-07-16 (session: TelcoAgent/KARMA review). Workstreams:

- **A — pipeline features (spec-agnostic):**
  A1 conflict grouping → review queue (`(from-id, rel-type)` groups with differing
  `to`-ids; also cross-label groups in `compare.py`);
  A2 `pipeline/align.py` alias suggester (embed canonical names + LLM surface forms;
  nearest-neighbor; distance < ρ → propose-only merge suggestion, ≥ ρ → new-entity
  proposal; backend: OpenAI-compatible `/v1/embeddings` via `SAGE_EMBED_BASE_URL`/
  `SAGE_EMBED_MODEL` (defaults to LLM base URL), `difflib` fallback, backend + distance
  stamped on every suggestion; output doubles as D-012 alias-table seed);
  A3 entity-pass-then-relation-pass instruction in `llm.build_messages()`;
  A4 one bounded retry when a chunk's response is non-empty but unparseable.
- **B — RRC enablement:** B1 fetch TS 38.331 **19.2.0** (match hand-built gold, not
  19.3.0); B2 SpecConfig template (C_RRC, `ue_clause_prefixes=("5.",)`, actor terms) +
  `--clauses` prefix filter in `pipeline.run`; B3 move controlled vocab from
  `extractors.py` into per-spec config; RRC lists (messages, timers, states,
  UE variables) from the hand-built pilot ontology; B4 `pipeline/gold/TS38331.json`
  (2–3 anchored few-shot examples derived from pilot facts).
- **C — runs + eval:** C1 three labels: `baseline` (as of be90466), `features`
  (A1+A2+A4), `features-p2` (+A3) — isolates the prompt change; C2
  `pipeline/eval_gold.py`: P/R of entities + relations vs hand-built pilot KG
  (clauses 5.3.3/5.3.5 only, curated concept-scheme entities excluded, both sides
  normalized through the alias mapping) + review-queue size, conflict-group count,
  anchor-warning count; C3 the KARMA-style number: fraction of pipeline-accepted LLM
  facts unsupported by gold (our local 83.1%-vs-0.625 analogue) → cite under the
  Layer-D flag; C4 write-up `docs/research/06-rrc-pipeline-vs-handbuilt.md`.
- Adjacent one-liner: `config.RELEASES` lacks Rel-20 (needed by the separate
  24.229 20.0.0 ingest Next item).
- Decision candidates at land time: conflict-grouping policy; alias-suggester design
  (backend, ρ, propose-only); per-spec vocab config.
- Sequencing: A3/A4/A1/B1/B2/B4 small & independent → B3 → A2 → C. Risk to check
  early: deterministic spine on 38.331 is thin until B3 — sanity-check UE filter +
  procedure anchors with `--dry-run` before LLM spend.
