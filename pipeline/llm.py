"""Model-agnostic LLM extractor (D-010 pipeline stage 3).

Talks to any **OpenAI-compatible** chat-completions endpoint (Ollama, vLLM, …)
configured purely via env — no SDK dependency (stdlib urllib only):

    SAGE_LLM_BASE_URL   e.g. http://localhost:11434/v1   (Ollama) or http://gpu:8000/v1 (vLLM)
    SAGE_LLM_MODEL      e.g. qwen2.5:32b-instruct
    SAGE_LLM_API_KEY    optional (vLLM/openai); ignored by Ollama
    SAGE_LLM_TIMEOUT    per-request timeout in seconds (default 300; local 32B models
                        on a busy GPU can take minutes per clause — raise if you hit
                        timeouts). Debug with: python3 -m pipeline.llm_debug --check
    SAGE_LLM_MAX_CLAUSE_CHARS
                        max clause-text chars per request (default 6000; 0 disables).
                        Clauses longer than this are split into chunks on paragraph
                        (newline) boundaries — see _chunk_text — so a slow local model
                        sees several short prompts instead of one huge one. Splitting
                        is deterministic (no LLM boundary detection): build_corpus.py
                        already stores paragraphs newline-separated, and each chunk is
                        a verbatim substring so anchors still resolve against the full
                        clause (KG ⊨ corpus). Facts from all chunks merge by id.
    SAGE_LLM_PROMPT_VARIANT
                        extraction system-prompt variant: "v1" (default) or "v2".
                        v2 adds the entity-pass-then-relation-pass instruction
                        (KARMA EEA→REA, research doc 05 §3.3). Kept switchable so
                        v1/v2 can be A/B-compared over the same corpus with
                        --label + pipeline.compare before v2 earns the default.
    SAGE_LLM_REASONING_SENTINEL
                        reasoning-model handling (mirrors NORA's design). Inline
                        <think>…</think> (also <thinking>/<reason>/<reasoning>)
                        blocks are ALWAYS stripped from the reply before JSON
                        parsing — that thinking prose contains '[' / ']' (clause
                        refs like [T300], lists) that would corrupt _parse's
                        bracket-bounded extraction; a no-op for models that never
                        emit the tags. Setting this to 1/true/yes/on additionally
                        activates the FINAL_ANSWER_MARKER sentinel for models whose
                        reasoning is UNtagged (plain prose): the system prompt then
                        instructs the model to print "===FINAL_ANSWER===" before
                        the JSON array and _strip_reasoning drops everything up to
                        it (prompt + strip stay in lockstep). Off by default.

If the endpoint is not configured (or ``--dry-run`` is passed to run.py), the
extractor runs in **stub mode**: it builds the few-shot prompt (so prompts are
inspectable now) but performs no network call and returns no facts. This lets the
whole deterministic spine run today; wiring the model later is just setting env.

Output contract (the model must return a JSON array; each item):
    {"subject": "...", "subject_type": "Procedure", "rel": "EXCHANGES",
     "object": "...", "object_type": "SIPMethod",
     "modality": "prose", "confidence": "high|med|low", "anchor": "<verbatim quote>"}
The anchor MUST be a verbatim span of the clause so KG⊨corpus holds.
"""
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request

from . import ids, ontology, records
from .error_codes import PipelineError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300            # local 32B models on a busy GPU routinely exceed 120s
_DEFAULT_MAX_CLAUSE_CHARS = 6000  # split longer clause text into paragraph-boundary chunks

# Reasoning ("thinking") models inline their chain-of-thought in the message
# content as <think>…</think> (or <thinking>/<reason>/<reasoning>) rather than
# splitting it into a separate reasoning_content field. We only want the final
# JSON, and that prose routinely contains '[' / ']' (clause refs like [T300],
# lists) that would corrupt _parse's bracket-bounded extraction — so strip the
# blocks. Endpoints that already separate reasoning never hit this; plain answers
# contain no such tags and pass through unchanged. (Mirrors NORA's
# core/src/llm/openai_provider.py._strip_reasoning.)
_THINK_TAGS = ("think", "thinking", "reason", "reasoning")
_THINK_BLOCK_RE = re.compile(
    r"<(" + "|".join(_THINK_TAGS) + r")\b[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(
    r"</(?:" + "|".join(_THINK_TAGS) + r")\s*>", re.IGNORECASE)

# Some reasoning models emit UNtagged chain-of-thought — plain prose before the
# answer, with no <think> delimiter to match. For those, the system prompt (see
# build_messages) instructs the model to print this sentinel on its own line just
# before the JSON array, and _strip_reasoning drops everything up to (and
# including) the last occurrence. This is a per-model opt-in: most models don't
# need it and shouldn't have their output reshaped, so it is OFF by default and
# the prompt instruction + strip are activated together — kept in lockstep — by
# SAGE_LLM_REASONING_SENTINEL. (Mirrors NORA's FINAL_ANSWER_MARKER /
# NORA_LLM_REASONING_SENTINEL pair.)
FINAL_ANSWER_MARKER = "===FINAL_ANSWER==="
ENV_REASONING_SENTINEL = "SAGE_LLM_REASONING_SENTINEL"


def reasoning_sentinel_enabled():
    """Whether the FINAL_ANSWER_MARKER sentinel is active (SAGE_LLM_REASONING_SENTINEL).

    Read live (not cached at import) so a run can toggle it via env. Truthy
    values: 1/true/yes/on."""
    return os.environ.get(ENV_REASONING_SENTINEL, "").strip().lower() in (
        "1", "true", "yes", "on")


def _strip_reasoning(text):
    """Remove reasoning from model output before JSON parsing.

    Handles (1) the prompt-driven FINAL_ANSWER_MARKER sentinel — only when
    reasoning_sentinel_enabled() — for untagged chain-of-thought, and (2) inline
    <think>…</think> tag blocks (always; harmless when absent). Idempotent and
    safe on normal answers: no marker/tags -> returned unchanged apart from
    surrounding whitespace.
    """
    if not text:
        return text
    # Sentinel: the only reliable signal for UNtagged reasoning, but opt-in per
    # model — most models don't need it and shouldn't have output reshaped.
    if reasoning_sentinel_enabled():
        marker_at = text.rfind(FINAL_ANSWER_MARKER)
        if marker_at != -1:
            text = text[marker_at + len(FINAL_ANSWER_MARKER):]
    cleaned = _THINK_BLOCK_RE.sub("", text)
    # Some servers drop the opening tag and return "reasoning…</think>answer" — a
    # dangling close with no matching open. Everything up to and including the
    # last such close tag is reasoning.
    matches = list(_THINK_CLOSE_RE.finditer(cleaned))
    if matches:
        cleaned = cleaned[matches[-1].end():]
    return cleaned.strip()


def max_clause_chars():
    raw = os.environ.get("SAGE_LLM_MAX_CLAUSE_CHARS")
    if raw is None:
        return _DEFAULT_MAX_CLAUSE_CHARS
    try:
        return int(raw)
    except ValueError:
        logger.warning("SAGE_LLM_MAX_CLAUSE_CHARS=%r is not an int — using %d",
                       raw, _DEFAULT_MAX_CLAUSE_CHARS)
        return _DEFAULT_MAX_CLAUSE_CHARS


def _hard_split(block, max_chars):
    """Last-resort split of a single over-long line into <= max_chars pieces.

    Breaks at the last space before the limit when there is one (keeping the space
    on the left piece), else cuts at the limit. ``"".join(pieces) == block`` — no
    characters are added or lost — so every piece stays a verbatim substring.
    """
    pieces = []
    s = block
    while len(s) > max_chars:
        cut = s.rfind(" ", 0, max_chars)
        cut = max_chars if cut <= 0 else cut + 1   # +1 keeps the space on the left
        pieces.append(s[:cut])
        s = s[cut:]
    if s:
        pieces.append(s)
    return pieces


def _chunk_text(text, max_chars):
    """Split clause text into chunks of <= max_chars, each a verbatim substring.

    Greedily packs newline-separated paragraphs without ever splitting one across a
    chunk (each chunk begins at a paragraph/line boundary). A single line longer
    than max_chars (e.g. a giant table block) is the only case that gets cut
    mid-line, via _hard_split — and even then on a real character index, so the
    piece is still a verbatim substring and its anchors resolve against the full
    clause (KG ⊨ corpus). Chunks are in-order, non-overlapping, and cover all the
    text (only the inter-paragraph '\\n' separators are dropped at chunk seams).
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    chunks, cur, cur_len = [], [], 0
    for para in text.split("\n"):
        if len(para) > max_chars:                  # over-long single line: flush, then hard-split
            if cur:
                chunks.append("\n".join(cur)); cur, cur_len = [], 0
            chunks.extend(_hard_split(para, max_chars))
            continue
        add = len(para) + (1 if cur else 0)        # +1 for the rejoining '\n'
        if cur and cur_len + add > max_chars:
            chunks.append("\n".join(cur))
            cur, cur_len, add = [], 0, len(para)
        cur.append(para)
        cur_len += add
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def endpoint(base_url=None, model=None, api_key=None):
    """Build an endpoint config. Explicit args win over env (for parallel runs that
    each target a different model/endpoint); anything unset falls back to env."""
    base = base_url or os.environ.get("SAGE_LLM_BASE_URL")
    if not base:
        return None
    try:
        timeout = int(os.environ.get("SAGE_LLM_TIMEOUT", _DEFAULT_TIMEOUT))
    except ValueError:
        logger.warning("SAGE_LLM_TIMEOUT=%r is not an int — using %ds",
                       os.environ.get("SAGE_LLM_TIMEOUT"), _DEFAULT_TIMEOUT)
        timeout = _DEFAULT_TIMEOUT
    ep = {"base": base.rstrip("/"),
          "model": model or os.environ.get("SAGE_LLM_MODEL", "qwen2.5:32b-instruct"),
          "key": api_key if api_key is not None else os.environ.get("SAGE_LLM_API_KEY", ""),
          "timeout": timeout}
    # api_key deliberately not logged.
    logger.info("LLM endpoint: base=%s model=%s timeout=%ds",
                ep["base"], ep["model"], ep["timeout"])
    return ep


def ontology_card():
    """Compact TBox the model must conform to (types + edge domain→range)."""
    ents = ", ".join(t for t in ontology.ENTITY_TYPES if t != "Entity")
    rels = "\n".join("  %s: %s -> %s" % (n, "/".join(s["domain"]), "/".join(s["range"]))
                     for n, s in ontology.RELATIONSHIP_TYPES.items())
    return "ENTITY TYPES:\n  %s\n\nRELATION TYPES (domain -> range):\n%s" % (ents, rels)


_SYSTEM_V1 = ("You extract a knowledge graph from 3GPP UE specification prose. "
              "Only output facts about the UE's behaviour that are explicitly stated. "
              "Conform to the ontology. Every fact's anchor MUST be a verbatim quote "
              "from the clause text. Return ONLY a JSON array, no prose.")

# v2 = v1 + entity-pass-then-relation-pass (KARMA EEA→REA via TelcoAgent; doc 05 §3.3).
# Two-pass decomposition first enumerates entities, then only relates enumerated
# entities — aimed at fewer hallucinated endpoints. Opt-in until A/B-validated.
_SYSTEM_V2 = _SYSTEM_V1 + (
    " Work in two passes before answering. PASS 1: enumerate every entity the clause"
    " explicitly names, with its ontology type. PASS 2: for pairs of PASS-1 entities"
    " only, assert the relations the clause explicitly states — never emit a fact"
    " whose subject or object you did not enumerate in PASS 1. Output only the final"
    " JSON array of PASS-2 facts.")

_SYSTEM = {"v1": _SYSTEM_V1, "v2": _SYSTEM_V2}

# Appended to the system prompt only when SAGE_LLM_REASONING_SENTINEL is on, so the
# instruction to emit the marker and _strip_reasoning's removal of it stay in
# lockstep (a model told to print it without the strip would leak the marker into
# the reply; the strip without the instruction would never see one).
_SENTINEL_INSTRUCTION = (
    " If you reason before answering, print the line " + FINAL_ANSWER_MARKER +
    " on its own line immediately before the JSON array, with nothing after that"
    " line except the array itself.")


def prompt_variant(variant=None):
    """Resolve the prompt variant: explicit arg > SAGE_LLM_PROMPT_VARIANT env > v1."""
    v = variant or os.environ.get("SAGE_LLM_PROMPT_VARIANT") or "v1"
    if v not in _SYSTEM:
        logger.warning("unknown prompt variant %r — using v1 (known: %s)",
                       v, ", ".join(sorted(_SYSTEM)))
        return "v1"
    return v


def build_messages(cfg, clause_key, clause, gold_examples, variant=None):
    sys = _SYSTEM[prompt_variant(variant)]
    if reasoning_sentinel_enabled():
        sys = sys + _SENTINEL_INSTRUCTION
    shots = "\n\n".join(
        "CLAUSE %s:\n%s\nFACTS:\n%s" % (ex["clause"], ex["text"], json.dumps(ex["facts"]))
        for ex in gold_examples)
    user = ("%s\n\n%s\n\nNow extract from:\nCLAUSE %s (%s):\n%s\nFACTS:"
            % (ontology_card(), shots, clause_key, clause.get("title", ""), clause.get("text", "")))
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _call(ep, messages, clause_key=""):
    """POST one chat-completion. Returns the assistant content string.

    Raises RuntimeError (with the API's error body / timeout context) on failure,
    so the orchestrator can report exactly which clause and why it died.
    """
    body = json.dumps({"model": ep["model"], "messages": messages,
                       "temperature": 0, "stream": False}).encode()
    req = urllib.request.Request(ep["base"] + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + ep["key"]})
    prompt_chars = sum(len(m["content"]) for m in messages)
    logger.debug("LLM call clause=%s model=%s prompt=%d chars timeout=%ds",
                 clause_key, ep["model"], prompt_chars, ep["timeout"])

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=ep["timeout"]) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as e:                # server answered with an error
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            err_body = "<no body>"
        err = PipelineError("LLM-E002", {"status": e.code, "reason": e.reason,
                                         "clause": clause_key, "body": err_body})
        logger.error(err.message)
        raise err from e
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        elapsed = time.time() - t0
        reason = getattr(e, "reason", e)
        timed_out = isinstance(reason, (socket.timeout, TimeoutError)) \
            or "timed out" in str(reason).lower()
        if timed_out:
            err = PipelineError("LLM-E001", {"secs": "%.0f" % elapsed,
                                             "limit": ep["timeout"], "clause": clause_key})
        else:
            err = PipelineError("LLM-E003", {"clause": clause_key, "reason": reason})
        logger.error("%s (after %.0fs)", err.message, elapsed)
        raise err from e

    elapsed = time.time() - t0
    choices = out.get("choices") or []
    if not choices:
        err = PipelineError("LLM-E004", {"clause": clause_key, "body": json.dumps(out)[:300]})
        logger.error(err.message)
        raise err
    content = (choices[0].get("message") or {}).get("content", "") or ""

    usage = out.get("usage") or {}
    ntok = int(usage.get("completion_tokens", 0) or 0)
    tps = (ntok / elapsed) if elapsed > 0 else 0.0
    logger.info("LLM clause=%s: %d tokens in %.1fs (%.1f tok/s), %d resp chars",
                clause_key, ntok, elapsed, tps, len(content))
    return content


def _parse(content):
    """Parse the model's reply into a list of facts.

    Returns the list on success (an explicit ``[]`` reply is a *valid* "no facts
    here" answer), or ``None`` when the reply has no parseable JSON array — the
    signal extract_clause's bounded retry keys off.

    A reasoning model's chain-of-thought span is stripped first (see
    _strip_reasoning / SAGE_LLM_THINK_SENTINEL) so brackets inside the thinking
    don't corrupt the bracket-bounded extraction below.
    """
    content = _strip_reasoning(content)
    s = content.find("["); e = content.rfind("]")
    if s == -1 or e == -1:
        return None
    try:
        parsed = json.loads(content[s:e + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _facts_to_records(cfg, clause_key, facts, ents, rels, rel_ids):
    """Fold parsed facts into the entity/relation accumulators. Returns #dropped.

    Provenance always uses ``clause_key`` (never a chunk label), so anchors
    resolve against the full clause text regardless of which chunk found them.
    """
    dropped = 0
    for f in facts:
        try:
            st, ot = f["subject_type"], f["object_type"]
            se = records.entity(cfg, st, f["subject"], clause_key, anchor=f.get("anchor"),
                                extractor="llm")
            oe = records.entity(cfg, ot, f["object"], clause_key, anchor=f.get("anchor"),
                                extractor="llm")
            ents[se["id"]] = se; ents[oe["id"]] = oe
            r = records.relation(
                cfg, f["rel"], se["id"], oe["id"], clause_key, anchor=f.get("anchor"),
                modality=f.get("modality", "prose"),
                confidence=f.get("confidence", "low"), procedure_ctx="llm", extractor="llm")
            if r["id"] not in rel_ids:      # dedup facts repeated across chunks
                rel_ids.add(r["id"]); rels.append(r)
        except (KeyError, TypeError):
            dropped += 1                   # malformed fact -> dropped (review covers gaps)
    return dropped


_RETRY_REMINDER = ("That reply was not a parseable JSON array. Return ONLY the JSON "
                   "array of facts for the clause above (or [] if there are none) — "
                   "no prose, no markdown fences.")


def extract_clause(cfg, clause_key, clause, gold_examples, ep=None, max_chars=None,
                   variant=None):
    """Return (entities, relations) for one clause. Stub -> ([], []) with no call.

    Long clauses are split into paragraph-boundary chunks (see _chunk_text) so a
    slow local model sees several short prompts; facts from all chunks are merged.
    A chunk whose reply is non-empty but unparseable gets exactly one retry with a
    terse format reminder (doc 05 §3.4); still unparseable -> 0 facts, logged (the
    review of gaps stays human).
    """
    if ep is None:
        return [], []                      # stub mode
    if max_chars is None:
        max_chars = max_clause_chars()
    text = clause.get("text") or ""
    chunks = _chunk_text(text, max_chars)
    if len(chunks) > 1:
        logger.info("clause=%s: %d chars > %d limit -> %d paragraph-boundary chunks",
                    clause_key, len(text), max_chars, len(chunks))

    ents, rels, rel_ids, total_facts = {}, [], set(), 0
    for i, ch in enumerate(chunks):
        ck = clause_key if len(chunks) == 1 else "%s#%d/%d" % (clause_key, i + 1, len(chunks))
        messages = build_messages(cfg, clause_key, dict(clause, text=ch), gold_examples,
                                  variant=variant)
        content = _call(ep, messages, ck)
        facts = _parse(content)
        if facts is None and content.strip():  # bounded retry: 1 attempt, then give up
            logger.warning("clause=%s: no parseable JSON array in %d-char response — retrying once",
                           ck, len(content))
            retry_messages = messages + [{"role": "assistant", "content": content},
                                         {"role": "user", "content": _RETRY_REMINDER}]
            content = _call(ep, retry_messages, ck + "+retry")
            facts = _parse(content)
            if facts is None:
                logger.warning("clause=%s: retry still unparseable (%d chars) — 0 facts from this chunk",
                               ck, len(content))
        facts = facts or []
        total_facts += len(facts)
        _facts_to_records(cfg, clause_key, facts, ents, rels, rel_ids)
    logger.debug("clause=%s: %d facts parsed -> %d entities, %d relations (across %d chunk(s))",
                 clause_key, total_facts, len(ents), len(rels), len(chunks))
    return list(ents.values()), rels
