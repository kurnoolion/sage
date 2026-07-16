"""LLM debug — probe an endpoint and verify SAGE's configured LLM (D-010 stage 3).

Mirrors NORA's core/src/llm/llm_debug.py debug-printing principles, against
SAGE's SAGE_LLM_* env wiring. Use this to diagnose a pipeline run that hangs or
times out *before* re-running the whole extraction.

Modes (pick one):

  python3 -m pipeline.llm_debug --probe http://gpu:8000
      Probe an HTTP endpoint to discover which API it speaks. Tests:
        GET  <url>/api/tags             — native Ollama (model list)
        GET  <url>/v1/models            — OpenAI-compatible (model list)
        POST <url>/v1/chat/completions  — OpenAI-compat chat shape
      Prints HTTP status + body excerpt per route, then a recommendation.

  python3 -m pipeline.llm_debug --check
      Resolve the endpoint from SAGE_LLM_* exactly as pipeline.run does, send one
      tiny completion ("ping"), and report latency. If one ping is slow, the
      per-clause extraction will be slower still — raise SAGE_LLM_TIMEOUT.

--check and --clause accept --llm-base-url / --llm-model / --llm-api-key, which
win over the SAGE_LLM_* env — same flags as pipeline.run, handy when comparing
two models without re-exporting.

  python3 -m pipeline.llm_debug --clause 5.1.1.1 [--spec "TS 24.229"] [--version 19.6.0]
                                [--no-call] [--out FILE]
      Show the EXACT prompt the pipeline builds for one clause (system + few-shot
      + clause text), then — unless --no-call — send it to the configured endpoint
      and print the full raw response and the parsed facts. This is the way to see
      "what was sent / what came back" for a real extraction. With --no-call (or no
      endpoint configured) it just prints the prompt (stub-inspectable). --out
      writes the dump to a file instead of stdout.

The API key is never echoed. --check sends a 3-token prompt, so it is cheap.
Note: --clause dumps corpus prose (the clause text + gold examples) — it is a
LOCAL operator diagnostic; do not paste its output into a cross-boundary report
(D-012b / D-017). A --out file lands wherever you point it (gitignore it).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from . import llm
from .run import load_gold


def _get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace")
            try:
                return resp.status, body[:300], json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body[:300], None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace") if e.fp else ""
        return e.code, body[:300], None
    except urllib.error.URLError as e:
        return 0, "URLError: %s" % (e.reason,), None
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e), None


def _post(url, body, headers=None, timeout=15):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode(errors="replace")
            return resp.status, text[:300]
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace") if e.fp else ""
        return e.code, text[:300]
    except urllib.error.URLError as e:
        return 0, "URLError: %s" % (e.reason,)
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e)


def _models(parsed):
    if not parsed:
        return ""
    items = parsed.get("models") or parsed.get("data") or []
    names = [it.get("name") or it.get("id") or it.get("model")
             for it in items if isinstance(it, dict)]
    names = [n for n in names if n]
    if len(names) > 8:
        return ", ".join(names[:8]) + ", … (+%d more)" % (len(names) - 8)
    return ", ".join(names)


def cmd_probe(url, api_key):
    base = url.rstrip("/")
    headers = {"Authorization": "Bearer %s" % api_key} if api_key else {}
    print("Probing endpoint: %s" % base)
    if api_key:
        print("Authorization: Bearer <redacted>")
    print("=" * 70)
    ollama = openai = False

    print("\n[1] GET /api/tags  (native Ollama model list)")
    st, body, parsed = _get("%s/api/tags" % base)
    print("    status: %s" % st)
    if st == 200:
        ollama = True
        print("    OK — native Ollama API confirmed")
        if _models(parsed):
            print("    models: %s" % _models(parsed))
    elif st == 0:
        print("    NETWORK: %s" % body)
    elif st == 404:
        print("    404 — not a native-Ollama endpoint")
    else:
        print("    body: %s" % body)

    print("\n[2] GET /v1/models  (OpenAI-compatible model list)")
    st, body, parsed = _get("%s/v1/models" % base, headers=headers)
    print("    status: %s" % st)
    if st == 200:
        openai = True
        print("    OK — OpenAI-compatible API confirmed")
        if _models(parsed):
            print("    models: %s" % _models(parsed))
    elif st == 401:
        print("    401 — exists but rejected (pass --api-key to retry)")
    elif st == 0:
        print("    NETWORK: %s" % body)
    elif st == 404:
        print("    404 — no /v1/models")
    else:
        print("    body: %s" % body)

    print("\n[3] POST /v1/chat/completions  (OpenAI-compat chat shape)")
    st, body = _post("%s/v1/chat/completions" % base,
                     {"model": "<probe>", "messages": [{"role": "user", "content": "ping"}]},
                     headers=headers, timeout=10)
    print("    status: %s" % st)
    if st in (200, 400, 401):
        openai = True
        print("    %s — endpoint understands the OpenAI chat shape" % st)
    elif st == 404:
        print("    404 — chat endpoint missing")
    elif st == 0:
        print("    NETWORK: %s" % body)
    else:
        print("    body: %s" % body[:120])

    print("\n" + "=" * 70 + "\nSUMMARY")
    print("  Native Ollama API:     %s" % ("YES" if ollama else "no"))
    print("  OpenAI-compatible API: %s" % ("YES" if openai else "no"))
    if openai:
        print("\nRecommended SAGE config:")
        print("  export SAGE_LLM_BASE_URL=%s/v1" % base)
        print("  export SAGE_LLM_MODEL=<model-name>      # see models list above")
        print("  export SAGE_LLM_API_KEY=<key>           # or any non-empty for Ollama")
        print("  # verify: python3 -m pipeline.llm_debug --check")
    elif ollama:
        print("\nNative-Ollama only. Point SAGE at its OpenAI surface:")
        print("  export SAGE_LLM_BASE_URL=%s/v1" % base)
    else:
        print("\nNeither API reachable — check URL, network, proxy/VPN, and that the server is up.")
    return 0 if (ollama or openai) else 1


def cmd_check(base_url=None, model=None, api_key=None):
    ep = llm.endpoint(base_url, model, api_key)
    if ep is None:
        print("No endpoint: SAGE_LLM_BASE_URL is not set and no --llm-base-url given "
              "(the pipeline would run in stub mode).")
        return 1
    print("Resolved endpoint: base=%s model=%s timeout=%ds" % (ep["base"], ep["model"], ep["timeout"]))
    print("Sending one-line probe completion 'ping' ...")
    messages = [{"role": "system", "content": "Reply with exactly one word."},
                {"role": "user", "content": "Reply with the single word: pong"}]
    t0 = time.time()
    try:
        content = llm._call(ep, messages, clause_key="<probe>")
    except Exception as e:
        print("  ERROR: %s" % e)
        print("  (If this is a timeout, the endpoint is up but slow — raise SAGE_LLM_TIMEOUT, "
              "or the model/base_url is wrong. Try --probe %s to confirm what it speaks.)" % ep["base"])
        return 2
    print("  completed in %.2fs" % (time.time() - t0))
    print("  response: %r" % (content[:200],))
    return 0


def cmd_clause(spec, version, clause_key, call, out, base_url=None, model=None, api_key=None):
    from . import config, corpus
    cfg = config.get(spec, version)
    cps = corpus.Corpus(cfg.store_dir)
    if clause_key not in cps:
        print("clause %r not in corpus %s %s (store=%s)" % (clause_key, spec, version, cfg.store_dir))
        return 1
    clause = cps[clause_key]
    gold = load_gold(spec).get("examples", [])
    messages = llm.build_messages(cfg, clause_key, clause, gold)

    sink = open(out, "w") if out else None

    def emit(s=""):
        print(s, file=sink) if sink else print(s)

    emit("# PROMPT for %s %s clause %s — %s" % (spec, version, clause_key, clause.get("title", "")))
    emit("# %d messages, %d gold examples, %d total chars"
         % (len(messages), len(gold), sum(len(m["content"]) for m in messages)))
    for m in messages:
        emit("\n================== %s ==================" % m["role"].upper())
        emit(m["content"])

    if not call:
        emit("\n# (--no-call) prompt only; not sent.")
        if sink:
            sink.close(); print("wrote prompt to %s" % out)
        return 0

    ep = llm.endpoint(base_url, model, api_key)
    if ep is None:
        emit("\n# no endpoint (SAGE_LLM_BASE_URL unset, no --llm-base-url) — cannot call "
             "(prompt shown above is what WOULD be sent).")
        if sink:
            sink.close(); print("wrote prompt to %s" % out)
        return 1

    emit("\n# sending to %s (model=%s, timeout=%ds) ..." % (ep["base"], ep["model"], ep["timeout"]))
    t0 = time.time()
    try:
        content = llm._call(ep, messages, clause_key=clause_key)
    except Exception as e:
        emit("\n# ERROR: %s" % e)
        if sink:
            sink.close(); print("wrote prompt+error to %s" % out)
        return 2
    emit("\n================== RAW RESPONSE (%d chars, %.1fs) =================="
         % (len(content), time.time() - t0))
    emit(content)
    facts = llm._parse(content)
    if facts is None:
        emit("\n================== PARSED FACTS ==================")
        emit("# response has no parseable JSON array (pipeline.run would retry once here)")
    else:
        emit("\n================== PARSED FACTS (%d) ==================" % len(facts))
        emit(json.dumps(facts, indent=2, ensure_ascii=False))
    if sink:
        sink.close(); print("wrote prompt+response to %s" % out)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Probe an LLM endpoint / verify SAGE's configured LLM.")
    ap.add_argument("--probe", metavar="URL", help="probe an HTTP endpoint for the API it speaks")
    ap.add_argument("--api-key", default=None, help="bearer token for --probe (optional)")
    ap.add_argument("--check", action="store_true",
                    help="resolve SAGE_LLM_* and send one ping completion, reporting latency")
    ap.add_argument("--clause", metavar="KEY",
                    help="show the real extraction prompt for this clause (and call the endpoint)")
    ap.add_argument("--spec", default="TS 24.229", help="spec for --clause (default: TS 24.229)")
    ap.add_argument("--version", default="19.6.0", help="version for --clause (default: 19.6.0)")
    ap.add_argument("--no-call", action="store_true", help="--clause: build/show the prompt but do not send it")
    ap.add_argument("--out", default=None, help="--clause: write the dump to this file instead of stdout")
    ap.add_argument("--llm-base-url", default=None, help="override SAGE_LLM_BASE_URL (--check/--clause)")
    ap.add_argument("--llm-model", default=None, help="override SAGE_LLM_MODEL (--check/--clause)")
    ap.add_argument("--llm-api-key", default=None, help="override SAGE_LLM_API_KEY (--check/--clause)")
    a = ap.parse_args()

    modes = [bool(a.probe), bool(a.check), bool(a.clause)]
    if sum(modes) != 1:                    # exactly one mode
        ap.print_help()
        print('\nPick exactly one mode: --probe URL | --check | --clause KEY')
        sys.exit(1)
    if a.probe:
        sys.exit(cmd_probe(a.probe, a.api_key))
    if a.check:
        sys.exit(cmd_check(a.llm_base_url, a.llm_model, a.llm_api_key))
    sys.exit(cmd_clause(a.spec, a.version, a.clause, not a.no_call, a.out,
                        a.llm_base_url, a.llm_model, a.llm_api_key))


if __name__ == "__main__":
    main()
