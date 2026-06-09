"""SAGE extraction pipeline — orchestrator / CLI (D-010).

    per-release:  UE filter -> deterministic extractors -> LLM extractor
                  -> merge -> validate -> snapshot (+ review queue)

Usage:
    python3 -m pipeline.run --spec "TS 24.229" --version 19.6.0 [--dry-run] [--limit N]

--dry-run forces LLM stub mode even if SAGE_LLM_BASE_URL is set. Without an
endpoint configured the LLM stage is automatically a no-op, so the deterministic
spine always runs.
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


def run(spec, version, dry_run=False, limit=None):
    cfg = config.get(spec, version)
    cps = corpus.Corpus(cfg.store_dir)

    # 1. UE filter
    ue_keys, ue_report = ue_filter.select(cps, cfg)

    # 2. deterministic extractors
    det_ents, det_rels = extractors.extract(cps, cfg, ue_keys)

    # 3. LLM extractor (stub unless endpoint configured and not --dry-run)
    ep = None if dry_run else llm.endpoint()
    gold = load_gold(spec)
    llm_ents, llm_rels = [], []
    if ep is not None:
        keys = [k for k in (ue_keys[:limit] if limit else ue_keys) if "/" not in k]
        total = len(keys)
        log.info("LLM stage: %d clauses to process (model=%s, timeout=%ds)",
                 total, ep["model"], ep["timeout"])
        t0 = time.time()
        for i, k in enumerate(keys, 1):
            log.info("[%d/%d] clause %s (%d chars)", i, total, k, len(cps[k].get("text") or ""))
            try:
                e, r = llm.extract_clause(cfg, k, cps[k], gold.get("examples", []), ep)
            except Exception as exc:       # report which clause died, then re-raise
                log.error("LLM stage aborted at clause %s (%d/%d) after %.0fs total: %s",
                          k, i, total, time.time() - t0, exc)
                raise
            llm_ents += e
            llm_rels += r
        log.info("LLM stage done: %d clauses in %.0fs -> %d entities, %d relations",
                 total, time.time() - t0, len(llm_ents), len(llm_rels))

    # 4. merge + validate
    entities = snapshot.merge(det_ents, llm_ents)
    relations = snapshot.merge(det_rels, llm_rels)
    errs, warns = validate.validate(entities, relations, cps, version)

    # 5. snapshot + review queue
    out_dir, paths = snapshot.write(cfg, entities, relations, errs, warns, ue_report)

    # report
    print("SAGE extraction — %s %s (%s)" % (cfg.spec, cfg.version, cfg.release))
    print("  UE filter:   kept %d / %d clauses (%s)" % (
        ue_report["kept"], ue_report["total_clauses"], ue_report["drop_reasons"]))
    print("  deterministic: %d entities, %d relations" % (len(det_ents), len(det_rels)))
    print("  llm:           %s" % ("stub (no endpoint)" if ep is None
                                   else "%d entities, %d relations" % (len(llm_ents), len(llm_rels))))
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
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="DEBUG logging (per-call request shapes, parsed-fact counts)")
    a = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S")
    run(a.spec, a.version, dry_run=a.dry_run, limit=a.limit)


if __name__ == "__main__":
    main()
