"""Alias suggester (KARMA entity normalization, adapted; doc 05 §3.2 + §5.3).

For every **LLM-extracted** entity whose id did not merge with a canonical
(deterministic-backbone) entity, find the nearest canonical name of a
*compatible type* and report it with a distance:

    distance <  ρ  ->  "merge" proposal      (surface form looks like an alias)
    distance >= ρ  ->  "new-entity" proposal (KARMA's ρ cutoff: don't force-map
                                              to the nearest neighbour)

Everything is **propose-only** (D-015): suggestions land in
``alias-suggestions.json`` + the review queue; nothing rewrites ids or merges
records. The suggestions file doubles as the seed of the D-012 alias table
(surface form -> canonical id, with evidence).

Backends (stamped on every suggestion):
  * ``embedding`` — OpenAI-compatible ``/v1/embeddings`` endpoint, stdlib-only
    HTTP like llm.py. Configured via env:
        SAGE_EMBED_MODEL     required to enable (e.g. nomic-embed-text,
                             bge-m3 — whatever the endpoint serves)
        SAGE_EMBED_BASE_URL  default: SAGE_LLM_BASE_URL
        SAGE_EMBED_API_KEY   default: SAGE_LLM_API_KEY
        SAGE_EMBED_BATCH     inputs per request (default 32 = TEI's
                             --max-client-batch-size); auto-halves on a 413
    Distance = cosine distance (1 - cosine similarity).
  * ``difflib`` — stdlib SequenceMatcher fallback, always available.
    Distance = 1 - ratio(lowercased labels). Lexical only: catches
    "RRC reconfiguration" ~ "RRCReconfiguration", misses semantic aliases.

ρ (SAGE_ALIGN_RHO, default 0.18) was tuned empirically on the TS 38.331 RRC run
(strand telcoagent-adoption, workstream C): the suggestions file reports the
best-neighbour distance for *every* surface entity, so the distribution was
inspected via ``align --stats`` and ρ chosen from where the marginal merge turns
more-likely-wrong-than-right. See the ``_DEFAULT_RHO`` note below for the crossover.
"""
import difflib
import json
import logging
import os
import re
import urllib.error
import urllib.request

from . import ontology

logger = logging.getLogger(__name__)

# Tuned empirically on the TS 38.331 RRC run (1182 surfaces, bge-m3), not a
# placeholder: at 0.35 every merge at the margin was a false pair; the precision
# crossover — where a marginal merge turns more-likely-wrong-than-right — sits in
# 0.15–0.20. 0.18 recovers the true aliases hiding at 0.15–0.16 while stopping
# before the 0.19–0.20 zone where false pairs dominate. The true-alias and
# distinct-but-related populations overlap in that band (a bi-encoder embeds short
# spec labels by topic), so no ρ separates them cleanly — a cross-encoder rerank
# of the borderline band is the real fix (future work). See `align --stats`.
_DEFAULT_RHO = 0.18


def rho():
    raw = os.environ.get("SAGE_ALIGN_RHO")
    if raw is None:
        return _DEFAULT_RHO
    try:
        return float(raw)
    except ValueError:
        logger.warning("SAGE_ALIGN_RHO=%r is not a float — using %s", raw, _DEFAULT_RHO)
        return _DEFAULT_RHO


# ---------------------------------------------------------------------------
# Embedding backend (OpenAI-compatible /embeddings; stdlib only)
# ---------------------------------------------------------------------------
def embed_endpoint():
    """Resolve the embeddings endpoint from env; None -> difflib fallback."""
    model = os.environ.get("SAGE_EMBED_MODEL")
    base = os.environ.get("SAGE_EMBED_BASE_URL") or os.environ.get("SAGE_LLM_BASE_URL")
    if not model or not base:
        return None
    key = os.environ.get("SAGE_EMBED_API_KEY", os.environ.get("SAGE_LLM_API_KEY", ""))
    return {"base": base.rstrip("/"), "model": model, "key": key}


# TEI's default --max-client-batch-size is 32; a larger request gets a 413
# (payload too large), which align.suggest would otherwise swallow into difflib.
_DEFAULT_EMBED_BATCH = 32


def _embed_batch_size():
    raw = os.environ.get("SAGE_EMBED_BATCH")
    if raw is None:
        return _DEFAULT_EMBED_BATCH
    try:
        n = int(raw)
        return n if n > 0 else _DEFAULT_EMBED_BATCH
    except ValueError:
        logger.warning("SAGE_EMBED_BATCH=%r is not an int — using %d",
                       raw, _DEFAULT_EMBED_BATCH)
        return _DEFAULT_EMBED_BATCH


def _embed_once(ep, texts):
    """One embeddings POST; vectors returned in the input order (by ``index``)."""
    body = json.dumps({"model": ep["model"], "input": texts}).encode()
    req = urllib.request.Request(
        ep["base"] + "/embeddings", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + ep["key"]})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    rows = sorted(data["data"], key=lambda d: d["index"])
    return [r["embedding"] for r in rows]


def _embed(ep, texts, batch=None):
    """Return one vector per text via the OpenAI-compatible embeddings API.

    Sends in batches of ``SAGE_EMBED_BATCH`` (default 32, matching TEI's
    ``--max-client-batch-size``). On a 413 the batch is halved and retried, so a
    server with a smaller cap (or unusually long inputs) degrades to smaller
    requests instead of failing the whole endpoint into difflib.
    """
    if batch is None:
        batch = _embed_batch_size()
    out, i, n = [], 0, len(texts)
    while i < n:
        chunk = texts[i:i + batch]
        try:
            out.extend(_embed_once(ep, chunk))
            i += len(chunk)
        except urllib.error.HTTPError as exc:
            if exc.code == 413 and len(chunk) > 1:
                batch = max(1, len(chunk) // 2)
                logger.warning("embeddings 413 (payload too large) — halving batch to %d",
                               batch)
                continue                       # retry the same start with a smaller chunk
            raise
    return out


def _cosine_distance(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - dot / (na * nb)


# ---------------------------------------------------------------------------
# Suggestion core
# ---------------------------------------------------------------------------
def _lexical_distance(a, b):
    """difflib distance with a containment heuristic: when one label appears as
    a whole word inside the other ("timer T300" ⊃ "T300", "the RRCSetup
    message" ⊃ "RRCSetup"), that's a strong alias signal that raw
    SequenceMatcher under-scores — cap the distance at 0.25 (< default ρ)."""
    a_l, b_l = a.lower(), b.lower()
    d = 1.0 - difflib.SequenceMatcher(None, a_l, b_l).ratio()
    short, long_ = (a_l, b_l) if len(a_l) <= len(b_l) else (b_l, a_l)
    if short and re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(short), long_):
        d = min(d, 0.25)
    return d


def _compatible(surface_type, canonical_type):
    """Types are comparable if equal or related in the subtype hierarchy —
    never suggest merging a Timer into a Procedure."""
    return (surface_type == canonical_type
            or ontology.is_a(surface_type, canonical_type)
            or ontology.is_a(canonical_type, surface_type))


def suggest(entities, rho_val=None):
    """Best canonical neighbour for each unmatched LLM entity.

    ``entities`` is the merged entity list (snapshot shape). Canonical set =
    deterministic-extractor entities; surface set = LLM entities whose id is
    not canonical (same id would already have merged). Returns (suggestions,
    backend_name); suggestions sorted by distance, every surface entity
    reported (the full distance distribution is the ρ-tuning data).
    """
    if rho_val is None:
        rho_val = rho()
    canonical = [e for e in entities if str(e.get("extractor", "")).startswith("deterministic")]
    canon_ids = {e["id"] for e in canonical}
    surfaces = [e for e in entities
                if e.get("extractor") == "llm" and e["id"] not in canon_ids]
    if not canonical or not surfaces:
        return [], "n/a"

    ep = embed_endpoint()
    backend = "embedding:%s" % ep["model"] if ep else "difflib"
    vecs = {}
    if ep:
        labels = [e["label"] for e in canonical] + [e["label"] for e in surfaces]
        try:
            vectors = _embed(ep, labels)
            vecs = dict(zip(labels, vectors))
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("embeddings endpoint failed (%s) — falling back to difflib", exc)
            ep, backend, vecs = None, "difflib", {}

    suggestions = []
    for s in surfaces:
        best = None
        for c in canonical:
            if not _compatible(s["type"], c["type"]):
                continue
            if ep:
                d = _cosine_distance(vecs[s["label"]], vecs[c["label"]])
            else:
                d = _lexical_distance(s["label"], c["label"])
            if best is None or d < best[0]:
                best = (d, c)
        if best is None:
            continue                        # no type-compatible canonical entity
        d, c = best
        suggestions.append({
            "surface_id": s["id"], "surface_label": s["label"], "surface_type": s["type"],
            "canonical_id": c["id"], "canonical_label": c["label"], "canonical_type": c["type"],
            "distance": round(d, 4), "backend": backend,
            "proposal": "merge" if d < rho_val else "new-entity",
        })
    suggestions.sort(key=lambda x: x["distance"])
    return suggestions, backend


def review_items(suggestions):
    """The merge proposals, as review-queue items (propose-only, D-015)."""
    return [{"kind": "alias-suggestion", "surface": s["surface_id"],
             "canonical": s["canonical_id"], "distance": s["distance"],
             "backend": s["backend"]}
            for s in suggestions if s["proposal"] == "merge"]


# ---------------------------------------------------------------------------
# Distance-distribution summary (ρ tuning)
# ---------------------------------------------------------------------------
_HIST_EDGES = [0, .05, .1, .15, .2, .25, .3, .35, .4, .45, .5, .6, .7, .8, .9, 1.01]


def _trunc(s, n=44):
    s = s or ""
    return s if len(s) <= n else s[:n - 1] + "…"


def distance_histogram(suggestions):
    """Counts per fixed distance bin, as ``[(lo, hi, count, cumulative), …]``."""
    n = len(suggestions)
    counts = [0] * (len(_HIST_EDGES) - 1)
    for s in suggestions:
        d = s["distance"]
        for i in range(len(_HIST_EDGES) - 1):
            if _HIST_EDGES[i] <= d < _HIST_EDGES[i + 1]:
                counts[i] += 1
                break
    rows, cum = [], 0
    for i, c in enumerate(counts):
        cum += c
        rows.append((_HIST_EDGES[i], _HIST_EDGES[i + 1], c, cum))
    return rows


def summarize(suggestions, rho_val, samples=8):
    """Print the distance histogram and the pairs straddling ρ.

    Proposals are recomputed from distance vs ``rho_val`` here (not read from the
    stored ``proposal`` field), so ``--stats --rho X`` shows what a *different* ρ
    would decide without re-embedding — distances don't depend on ρ.
    """
    n = len(suggestions)
    if not n:
        print("  (no surfaces to summarize)")
        return
    ordered = sorted(suggestions, key=lambda x: x["distance"])
    below = [x for x in ordered if x["distance"] < rho_val]
    above = [x for x in ordered if x["distance"] >= rho_val]
    print("  rho=%.3f -> %d merge / %d new-entity (of %d)" % (rho_val, len(below), len(above), n))
    print("  distance histogram (count, cumulative %):")
    for lo, hi, c, cum in distance_histogram(suggestions):
        bar = "#" * int(round(40.0 * c / n)) if n else ""
        print("    [%.2f,%.2f) %5d  %5.1f%%  %s" % (lo, hi, c, 100.0 * cum / n, bar))
    if below:
        print("  boundary — last %d merges just below rho (borderline-in):"
              % min(samples, len(below)))
        for x in below[-samples:]:
            print("    %.3f  %s  ->  %s"
                  % (x["distance"], _trunc(x["surface_label"]), _trunc(x["canonical_label"])))
    if above:
        print("  boundary — first %d at/above rho (borderline-out):"
              % min(samples, len(above)))
        for x in above[:samples]:
            print("    %.3f  %s  ->  %s"
                  % (x["distance"], _trunc(x["surface_label"]), _trunc(x["canonical_label"])))


# ---------------------------------------------------------------------------
# CLI — recompute alignment on an existing snapshot, or (--stats) summarize the
# distance distribution to tune ρ. Both derive every path from --spec/--version/
# --label; --stats --rho X previews a cutoff without re-embedding.
# ---------------------------------------------------------------------------
def main():
    import argparse
    from . import snapshot

    ap = argparse.ArgumentParser(
        description="(Re)compute alias suggestions for an existing snapshot, or "
                    "(--stats) summarize the distance distribution for ρ tuning.")
    ap.add_argument("--spec", default="TS 24.229")
    ap.add_argument("--version", default="19.6.0")
    ap.add_argument("--label", default=None)
    ap.add_argument("--rho", type=float, default=None, help="override SAGE_ALIGN_RHO")
    ap.add_argument("--stats", action="store_true",
                    help="summarize the EXISTING alias-suggestions.json (histogram + "
                         "ρ-boundary pairs) without recomputing or hitting the endpoint; "
                         "combine with --rho to preview a different cutoff for free")
    ap.add_argument("--samples", type=int, default=8,
                    help="ρ-boundary pairs to show per side (default 8)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    snap_dir = snapshot.dir_for(a.spec, a.version, a.label)
    out = os.path.join(snap_dir, "alias-suggestions.json")

    # --stats: analyze the file we already wrote — no snapshot load, no endpoint.
    if a.stats:
        if not os.path.exists(out):
            raise SystemExit("no alias-suggestions.json at %s — run without --stats first" % out)
        with open(out) as f:
            data = json.load(f)
        suggestions = data.get("suggestions", [])
        rho_val = a.rho if a.rho is not None else (data.get("rho") if data.get("rho") is not None else rho())
        print("alias suggestions: %d scored (%s), file rho=%s%s"
              % (len(suggestions), data.get("backend"), data.get("rho"),
                 "  [previewing rho=%s]" % rho_val if a.rho is not None else ""))
        summarize(suggestions, rho_val, a.samples)
        print("source -> %s" % out)
        return

    with open(os.path.join(snap_dir, "snapshot.json")) as f:
        snap = json.load(f)
    suggestions, backend = suggest(snap["entities"], a.rho)
    rho_val = a.rho if a.rho is not None else rho()
    with open(out, "w") as f:
        json.dump({"spec": a.spec, "version": a.version, "backend": backend,
                   "rho": rho_val, "suggestions": suggestions}, f, indent=2, ensure_ascii=False)
    merges = sum(1 for s in suggestions if s["proposal"] == "merge")
    print("alias suggestions: %d surface entities scored (%s), %d merge proposals (rho=%s)"
          % (len(suggestions), backend, merges, rho_val))
    summarize(suggestions, rho_val, a.samples)
    print("full list -> %s" % out)


if __name__ == "__main__":
    main()
