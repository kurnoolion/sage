"""SAGE extraction pipeline — orchestrator / CLI (D-010).

    per-release:  UE filter -> deterministic extractors -> LLM extractor
                  -> merge -> validate -> snapshot (+ review queue)

Usage:
    python3 -m pipeline.run --spec "TS 24.229" --version 19.6.0 [--dry-run] [--limit N]
                            [--progress-every N] [--checkpoint-every N]
                            [--label NAME] [--llm-base-url URL] [--llm-model M] [--llm-api-key K]
                            [--max-tokens N]

--dry-run forces LLM stub mode even if SAGE_LLM_BASE_URL is set. Without an
endpoint configured the LLM stage is automatically a no-op, so the deterministic
spine always runs.

--progress-every N logs a cumulative progress line (clauses done, facts so far,
elapsed, ETA) every N clauses (default 25; 0 disables). --checkpoint-every N
writes the partial graph to the snapshot every N clauses (default 0 = off) so you
can open it in the viewer mid-run; the final snapshot is always written.

To run several LLMs in PARALLEL over the same corpus, give each run its own
--label and --llm-model/--llm-base-url (the snapshot lands in a per-label sub-dir,
so concurrent processes don't collide), then diff them with `pipeline.compare`:

    python3 -m pipeline.run --version 19.6.0 --label qwen  --llm-model qwen2.5:32b   &
    python3 -m pipeline.run --version 19.6.0 --label llama --llm-model llama3.1:70b  &
    wait
    python3 -m pipeline.compare --version 19.6.0 qwen llama
"""
import argparse
import json
import logging
import os
import time

from . import config, corpus, extractors, llm, snapshot, ue_filter, validate

log = logging.getLogger(__name__)


def load_gold(spec):
    path = os.path.join("pipeline", "gold", spec.replace(" ", "").replace(".", "") + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"examples": []}


def _fmt_dur(secs):
    secs = int(secs)
    if secs < 60:
        return "%ds" % secs
    if secs < 3600:
        return "%dm%02ds" % (secs // 60, secs % 60)
    return "%dh%02dm" % (secs // 3600, (secs % 3600) // 60)


def _build_and_write(cfg, det_ents, det_rels, llm_ents, llm_rels, cps, version, ue_report, label=None):
    """Merge deterministic + LLM records, validate, and write the snapshot.

    Used for the final write and for mid-run checkpoints. merge() de-dups by id
    and is idempotent on provenance, so repeated checkpoint calls are safe.
    """
    entities = snapshot.merge(det_ents, llm_ents)
    relations = snapshot.merge(det_rels, llm_rels)
    errs, warns = validate.validate(entities, relations, cps, version)
    out_dir, paths = snapshot.write(cfg, entities, relations, errs, warns, ue_report, label=label)
    return entities, relations, errs, warns, out_dir, paths


def _scope_to_clauses(ue_keys, clauses):
    """Restrict UE keys to the given clause-number prefixes (e.g. "5.3.3,5.3.5").

    A prefix matches itself, its sub-clauses ("5.3.3.4"), and its named
    sub-units ("5.3.3.4/tab-x") — but not lookalike siblings ("5.3.30").
    Scoping applies to the whole run (deterministic + LLM), so a scoped
    snapshot contains only facts from those clauses — the mode the RRC
    pilot rebuild-and-compare uses.
    """
    if not clauses:
        return ue_keys
    prefixes = [c.strip() for c in clauses.split(",") if c.strip()]
    return [k for k in ue_keys
            if any(k == p or k.startswith(p + ".") or k.startswith(p + "/")
                   for p in prefixes)]


def run(spec, version, dry_run=False, limit=None, progress_every=25, checkpoint_every=0,
        label=None, llm_base_url=None, llm_model=None, llm_api_key=None, prompt_variant=None,
        clauses=None, max_tokens=None):
    cfg = config.get(spec, version)
    cps = corpus.Corpus(cfg.store_dir)

    # 1. UE filter
    ue_keys, ue_report = ue_filter.select(cps, cfg)
    if clauses:
        before = len(ue_keys)
        ue_keys = _scope_to_clauses(ue_keys, clauses)
        ue_report["clause_scope"] = {"prefixes": clauses, "kept": len(ue_keys),
                                     "of_ue_filtered": before}
        log.info("clause scope %s: %d of %d UE clauses kept", clauses, len(ue_keys), before)

    # 2. deterministic extractors
    det_ents, det_rels = extractors.extract(cps, cfg, ue_keys)

    # 3. LLM extractor (stub unless endpoint configured and not --dry-run)
    ep = None if dry_run else llm.endpoint(llm_base_url, llm_model, llm_api_key, max_tokens)
    gold = load_gold(spec)
    llm_ents, llm_rels = [], []
    if ep is not None:
        keys = [k for k in (ue_keys[:limit] if limit else ue_keys) if "/" not in k]
        total = len(keys)
        log.info("LLM stage%s: %d clauses to process (model=%s, timeout=%ds, max_clause_chars=%d, prompt=%s)",
                 " [%s]" % label if label else "", total, ep["model"], ep["timeout"],
                 llm.max_clause_chars(), llm.prompt_variant(prompt_variant))
        t0 = time.time()
        for i, k in enumerate(keys, 1):
            log.info("[%d/%d] clause %s (%d chars)", i, total, k, len(cps[k].get("text") or ""))
            try:
                e, r = llm.extract_clause(cfg, k, cps[k], gold.get("examples", []), ep,
                                          variant=prompt_variant)
            except Exception as exc:       # report which clause died, then re-raise
                log.error("LLM stage aborted at clause %s (%d/%d) after %.0fs total: %s",
                          k, i, total, time.time() - t0, exc)
                raise
            llm_ents += e
            llm_rels += r

            if progress_every and i % progress_every == 0 and i < total:
                elapsed = time.time() - t0
                eta = elapsed / i * (total - i)
                log.info("  progress: %d/%d clauses (%.0f%%), %d LLM facts so far (pre-merge), "
                         "%s elapsed, ~%s remaining",
                         i, total, 100.0 * i / total, len(llm_rels), _fmt_dur(elapsed), _fmt_dur(eta))

            if checkpoint_every and i % checkpoint_every == 0 and i < total:
                cp_ents, cp_rels, cp_errs, _, cp_dir, _ = _build_and_write(
                    cfg, det_ents, det_rels, llm_ents, llm_rels, cps, version, ue_report, label)
                log.info("  checkpoint: partial graph after %d/%d clauses -> %s "
                         "(%d entities, %d relations, %d errors) — open it in the viewer",
                         i, total, cp_dir, len(cp_ents), len(cp_rels), len(cp_errs))

        log.info("LLM stage done: %d clauses in %s -> %d entities, %d relations (pre-merge)",
                 total, _fmt_dur(time.time() - t0), len(llm_ents), len(llm_rels))

    # 4 + 5. merge + validate + snapshot (also the path taken for dry-run / stub)
    entities, relations, errs, warns, out_dir, paths = _build_and_write(
        cfg, det_ents, det_rels, llm_ents, llm_rels, cps, version, ue_report, label)

    # report
    print("SAGE extraction — %s %s (%s)%s" % (
        cfg.spec, cfg.version, cfg.release, " [label=%s]" % label if label else ""))
    print("  UE filter:   kept %d / %d clauses (%s)" % (
        ue_report["kept"], ue_report["total_clauses"], ue_report["drop_reasons"]))
    print("  deterministic: %d entities, %d relations" % (len(det_ents), len(det_rels)))
    print("  llm:           %s" % ("stub (no endpoint)" if ep is None
                                   else "model=%s -> %d entities, %d relations" % (
                                       ep["model"], len(llm_ents), len(llm_rels))))
    print("  merged:        %d entities, %d relations" % (len(entities), len(relations)))
    print("  validation:    %d errors, %d warnings" % (len(errs), len(warns)))
    for e in errs[:10]:
        print("    ERROR:", e)
    print("  snapshot ->    %s" % out_dir)
    by_type = {}
    for e in entities:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    print("  entity types:  %s" % dict(sorted(by_type.items(), key=lambda kv: -kv[1])))
    return out_dir, errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="TS 24.229")
    ap.add_argument("--version", default="19.6.0")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--progress-every", type=int, default=25,
                    help="cumulative progress line every N clauses (0 disables; default 25)")
    ap.add_argument("--checkpoint-every", type=int, default=0,
                    help="write the partial graph every N clauses for mid-run viewing (default 0 = off)")
    ap.add_argument("--label", default=None,
                    help="run label (e.g. model name); namespaces the snapshot dir for parallel runs")
    ap.add_argument("--llm-base-url", default=None, help="override SAGE_LLM_BASE_URL for this run")
    ap.add_argument("--llm-model", default=None, help="override SAGE_LLM_MODEL for this run")
    ap.add_argument("--llm-api-key", default=None, help="override SAGE_LLM_API_KEY for this run")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="override SAGE_LLM_MAX_TOKENS (max completion tokens; raise if replies "
                         "truncate at finish_reason=length)")
    ap.add_argument("--prompt-variant", default=None, choices=("v1", "v2"),
                    help="extraction prompt variant (default: SAGE_LLM_PROMPT_VARIANT or v1; "
                         "v2 = entity-pass-then-relation-pass)")
    ap.add_argument("--clauses", default=None,
                    help="comma-separated clause-number prefixes to scope the whole run to "
                         "(e.g. '5.3.3,5.3.5'); default: all UE-filtered clauses")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="DEBUG logging (per-call request shapes, parsed-fact counts)")
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S")
    run(a.spec, a.version, dry_run=a.dry_run, limit=a.limit,
        progress_every=a.progress_every, checkpoint_every=a.checkpoint_every,
        label=a.label, llm_base_url=a.llm_base_url, llm_model=a.llm_model,
        llm_api_key=a.llm_api_key, prompt_variant=a.prompt_variant, clauses=a.clauses,
        max_tokens=a.max_tokens)


if __name__ == "__main__":
    main()
