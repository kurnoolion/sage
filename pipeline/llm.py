"""Model-agnostic LLM extractor (D-010 pipeline stage 3).

Talks to any **OpenAI-compatible** chat-completions endpoint (Ollama, vLLM, …)
configured purely via env — no SDK dependency (stdlib urllib only):

    SAGE_LLM_BASE_URL   e.g. http://localhost:11434/v1   (Ollama) or http://gpu:8000/v1 (vLLM)
    SAGE_LLM_MODEL      e.g. qwen2.5:32b-instruct
    SAGE_LLM_API_KEY    optional (vLLM/openai); ignored by Ollama
    SAGE_LLM_TIMEOUT    per-request timeout in seconds (default 300; local 32B models
                        on a busy GPU can take minutes per clause — raise if you hit
                        timeouts). Debug with: python3 -m pipeline.llm_debug --check

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
import socket
import time
import urllib.error
import urllib.request

from . import ids, ontology, records
from .error_codes import PipelineError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300       # local 32B models on a busy GPU routinely exceed 120s


def endpoint():
    base = os.environ.get("SAGE_LLM_BASE_URL")
    if not base:
        return None
    try:
        timeout = int(os.environ.get("SAGE_LLM_TIMEOUT", _DEFAULT_TIMEOUT))
    except ValueError:
        logger.warning("SAGE_LLM_TIMEOUT=%r is not an int — using %ds",
                       os.environ.get("SAGE_LLM_TIMEOUT"), _DEFAULT_TIMEOUT)
        timeout = _DEFAULT_TIMEOUT
    ep = {"base": base.rstrip("/"),
          "model": os.environ.get("SAGE_LLM_MODEL", "qwen2.5:32b-instruct"),
          "key": os.environ.get("SAGE_LLM_API_KEY", ""),
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


def build_messages(cfg, clause_key, clause, gold_examples):
    sys = ("You extract a knowledge graph from 3GPP UE specification prose. "
           "Only output facts about the UE's behaviour that are explicitly stated. "
           "Conform to the ontology. Every fact's anchor MUST be a verbatim quote "
           "from the clause text. Return ONLY a JSON array, no prose.")
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
    s = content.find("["); e = content.rfind("]")
    if s == -1 or e == -1:
        return []
    try:
        return json.loads(content[s:e + 1])
    except json.JSONDecodeError:
        return []


def extract_clause(cfg, clause_key, clause, gold_examples, ep=None):
    """Return (entities, relations) for one clause. Stub -> ([], []) with no call."""
    messages = build_messages(cfg, clause_key, clause, gold_examples)
    if ep is None:
        return [], []                      # stub mode
    content = _call(ep, messages, clause_key)
    facts = _parse(content)
    if not facts and content.strip():
        logger.debug("clause=%s: response had no parseable JSON array (%d chars)",
                     clause_key, len(content))
    ents, rels, dropped = {}, [], 0
    for f in facts:
        try:
            st, ot = f["subject_type"], f["object_type"]
            se = records.entity(cfg, st, f["subject"], clause_key, anchor=f.get("anchor"),
                                extractor="llm")
            oe = records.entity(cfg, ot, f["object"], clause_key, anchor=f.get("anchor"),
                                extractor="llm")
            ents[se["id"]] = se; ents[oe["id"]] = oe
            rels.append(records.relation(
                cfg, f["rel"], se["id"], oe["id"], clause_key, anchor=f.get("anchor"),
                modality=f.get("modality", "prose"),
                confidence=f.get("confidence", "low"), procedure_ctx="llm", extractor="llm"))
        except (KeyError, TypeError):
            dropped += 1                   # malformed fact -> dropped (review covers gaps)
    logger.debug("clause=%s: %d facts parsed -> %d entities, %d relations (%d malformed dropped)",
                 clause_key, len(facts), len(ents), len(rels), dropped)
    return list(ents.values()), rels
