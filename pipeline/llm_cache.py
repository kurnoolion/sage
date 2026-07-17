"""Resumable per-clause LLM cache (D-0xx).

The LLM stage can die mid-run — an endpoint that 500s past the retry budget, a
Ctrl-C, an OOM. To make a restart cheap (and to not throw away minutes of local
inference), each clause's extracted facts are appended to a JSONL cache the
instant they are produced. On ``--resume`` the cache is replayed: clauses already
present are reused *without* calling the model, and the run continues from the
first one missing.

Layout — ``<snapshot-dir>/llm-cache.jsonl`` (gitignored with the rest of the
snapshot):

    {"_header": {spec, version, model, prompt_variant, max_clause_chars, sentinel}}
    {"clause": "5.3.3.2", "entities": [...], "relations": [...]}
    {"clause": "5.3.3.4", "entities": [...], "relations": [...]}
    ...

The header pins the parameters that change extraction *output*. A resume against
a cache whose header disagrees is refused (HeaderMismatch) — silently mixing two
prompt variants / models / chunk sizes into one graph would be worse than
starting over. A clause that legitimately yields zero facts still gets a line, so
"already done" is never confused with "found nothing".

Only stdlib; each record is flushed immediately so a hard abort keeps every
completed clause. A torn final line (crash mid-write) is skipped on read.
"""
import json
import os

CACHE_NAME = "llm-cache.jsonl"

# fields that affect what the LLM emits — a resume must match on all of them
_HEADER_KEYS = ("spec", "version", "model", "prompt_variant", "max_clause_chars", "sentinel")


class HeaderMismatch(RuntimeError):
    """Raised when --resume finds a cache built with different extraction params."""


def cache_path(snap_dir):
    return os.path.join(snap_dir, CACHE_NAME)


def build_header(spec, version, model, prompt_variant, max_clause_chars, sentinel):
    return {"spec": spec, "version": version, "model": model,
            "prompt_variant": prompt_variant, "max_clause_chars": max_clause_chars,
            "sentinel": bool(sentinel)}


def read(snap_dir):
    """Return ``(header, {clause: {"entities": [...], "relations": [...]}})``.

    ``header`` is None and the map empty when no cache exists. A malformed line
    (e.g. a final record torn by a crash mid-write) is skipped, not fatal.
    """
    path = cache_path(snap_dir)
    header, done = None, {}
    if not os.path.exists(path):
        return header, done
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue                       # torn final line from a crash — ignore
            if "_header" in rec:
                header = rec["_header"]
            elif "clause" in rec:
                done[rec["clause"]] = rec
    return header, done


class Writer:
    """Append-only writer for the per-clause cache.

    ``resume=True`` keeps an existing cache and appends to it; otherwise the file
    is truncated and a fresh header written. Each ``add`` is flushed so a later
    abort still leaves every completed clause on disk.
    """

    def __init__(self, snap_dir, header, resume=False):
        os.makedirs(snap_dir, exist_ok=True)
        self.path = cache_path(snap_dir)
        keep = resume and os.path.exists(self.path)
        self._f = open(self.path, "a" if keep else "w")
        if not keep:
            self._write({"_header": header})

    def _write(self, rec):
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()

    def add(self, clause, entities, relations):
        self._write({"clause": clause, "entities": entities, "relations": relations})

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def check_header(existing, current):
    """Raise HeaderMismatch if a resume's cached params differ from this run's.

    Compares only the extraction-affecting keys, so an older cache missing a newer
    key (treated as its current value) still resumes cleanly.
    """
    if existing is None:
        return
    diffs = {k: (existing.get(k), current.get(k))
             for k in _HEADER_KEYS if existing.get(k) != current.get(k)}
    if diffs:
        raise HeaderMismatch(
            "cached extraction params differ from this run — refusing to resume "
            "(pass a fresh --label, or drop --resume to overwrite): "
            + ", ".join("%s cache=%r now=%r" % (k, a, b) for k, (a, b) in sorted(diffs.items())))
