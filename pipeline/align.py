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

ρ (SAGE_ALIGN_RHO, default 0.35) is a placeholder until tuned empirically —
the suggestions file reports the best-neighbour distance for *every* surface
entity precisely so the distribution can be inspected and ρ chosen from data
(strand telcoagent-adoption, workstream C).
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

_DEFAULT_RHO = 0.35


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
# CLI — re-run alignment on an existing snapshot (ρ tuning without re-extract)
# ---------------------------------------------------------------------------
def main():
    import argparse
    from . import snapshot

    ap = argparse.ArgumentParser(
        description="(Re)compute alias suggestions for an existing snapshot.")
    ap.add_argument("--spec", default="TS 24.229")
    ap.add_argument("--version", default="19.6.0")
    ap.add_argument("--label", default=None)
    ap.add_argument("--rho", type=float, default=None, help="override SAGE_ALIGN_RHO")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    snap_dir = snapshot.dir_for(a.spec, a.version, a.label)
    with open(os.path.join(snap_dir, "snapshot.json")) as f:
        snap = json.load(f)
    suggestions, backend = suggest(snap["entities"], a.rho)
    out = os.path.join(snap_dir, "alias-suggestions.json")
    with open(out, "w") as f:
        json.dump({"spec": a.spec, "version": a.version, "backend": backend,
                   "rho": a.rho if a.rho is not None else rho(),
                   "suggestions": suggestions}, f, indent=2, ensure_ascii=False)
    merges = sum(1 for s in suggestions if s["proposal"] == "merge")
    print("alias suggestions: %d surface entities scored (%s), %d merge proposals (rho=%s)"
          % (len(suggestions), backend, merges, a.rho if a.rho is not None else rho()))
    for s in suggestions[:10]:
        print("  %.3f %-12s %s (%s) -> %s (%s)"
              % (s["distance"], s["proposal"], s["surface_label"], s["surface_type"],
                 s["canonical_label"], s["canonical_type"]))
    print("full list -> %s" % out)


if __name__ == "__main__":
    main()
