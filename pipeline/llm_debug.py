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

The API key is never echoed. --check sends a 3-token prompt, so it is cheap.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from . import llm


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


def cmd_check():
    ep = llm.endpoint()
    if ep is None:
        print("SAGE_LLM_BASE_URL is not set — nothing to check (the pipeline would run in stub mode).")
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


def main():
    ap = argparse.ArgumentParser(description="Probe an LLM endpoint / verify SAGE's configured LLM.")
    ap.add_argument("--probe", metavar="URL", help="probe an HTTP endpoint for the API it speaks")
    ap.add_argument("--api-key", default=None, help="bearer token for --probe (optional)")
    ap.add_argument("--check", action="store_true",
                    help="resolve SAGE_LLM_* and send one ping completion, reporting latency")
    a = ap.parse_args()

    if bool(a.probe) == bool(a.check):     # exactly one mode
        ap.print_help()
        print('\nPick exactly one mode: --probe URL | --check')
        sys.exit(1)
    if a.probe:
        sys.exit(cmd_probe(a.probe, a.api_key))
    sys.exit(cmd_check())


if __name__ == "__main__":
    main()
