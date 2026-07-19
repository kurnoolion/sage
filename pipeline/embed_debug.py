"""Embeddings debug — diagnose the alias suggester's embedding backend (D-015).

When ``align.suggest`` cannot reach an embeddings endpoint it logs one line and
silently degrades to difflib:

    align WARNING embeddings endpoint failed (HTTP Error 405: Method Not Allowed)
                  - falling back to difflib

difflib is lexical only, so the ρ distribution it produces is not the one D-015
wants to tune against — a fallback is a *quiet* loss of quality. This tool finds
out why the endpoint failed and what to export instead.

Usage:
    python3 -m pipeline.embed_debug                  # resolve env, probe candidates
    python3 -m pipeline.embed_debug --base URL --model M   # try an explicit pair
    python3 -m pipeline.embed_debug --end-to-end     # also run align._embed itself

What it does:
  1. Resolves the endpoint exactly as ``align.embed_endpoint()`` does and prints
     the URL align.py would POST to (base + "/embeddings").
  2. Confirms the host is reachable and lists the models it serves, so a wrong
     *host* is not mistaken for a missing embeddings *route*.
  3. POSTs a two-string batch to every plausible embeddings route and reports
     status, the Allow header on a 405, and a body excerpt. A 405 means the path
     exists but rejects POST — usually the route is wrong or the server serves
     chat only.
  4. Checks the *shape* of any 200: align.py needs OpenAI's
     ``{"data": [{"index": i, "embedding": [...]}]}``. A server answering 200
     with Ollama's native shape still breaks align.py — on KeyError it takes the
     same silent difflib fallback. This is easy to miss without a shape check.
  5. Prints the exact export needed to make align.py use the working route.

The API key is never echoed. Inputs are two short literals, so this is cheap.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from . import align

# Two short strings; if they embed, real labels will too.
PROBE_INPUT = ["RRCReconfiguration", "RRC reconfiguration"]


def _post(url, body, key, timeout=30):
    """POST json; return (status, allow_header, body_text, parsed_or_None)."""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode(errors="replace")
            try:
                return resp.status, "", text, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, "", text, None
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace") if e.fp else ""
        return e.code, e.headers.get("Allow", "") if e.headers else "", text, None
    except urllib.error.URLError as e:
        return 0, "", "URLError: %s" % (e.reason,), None
    except Exception as e:
        return 0, "", "%s: %s" % (type(e).__name__, e), None


def _get(url, key, timeout=15):
    headers = {"Authorization": "Bearer " + key} if key else {}
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode(errors="replace")
            try:
                return resp.status, text, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text, None
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode(errors="replace") if e.fp else ""), None
    except urllib.error.URLError as e:
        return 0, "URLError: %s" % (e.reason,), None
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e), None


def _root(base):
    """Strip a trailing /v1 so both '<host>' and '<host>/v1' style bases work."""
    b = base.rstrip("/")
    return b[:-3].rstrip("/") if b.endswith("/v1") else b


def candidates(base, model):
    """Plausible embeddings routes, in the order worth trying.

    Each entry is (label, url, payload, shape) where shape names the response
    contract: "openai" is the only one align.py can consume today.
    """
    b, r = base.rstrip("/"), _root(base)
    seen, out = set(), []

    def add(label, url, payload, shape):
        if url not in seen:
            seen.add(url)
            out.append((label, url, payload, shape))

    oa = {"model": model, "input": PROBE_INPUT}
    add("align.py's route", b + "/embeddings", oa, "openai")
    add("OpenAI under base", b + "/v1/embeddings", oa, "openai")
    add("OpenAI under root", r + "/v1/embeddings", oa, "openai")
    add("bare under root", r + "/embeddings", oa, "openai")
    add("Ollama native (new)", r + "/api/embed", {"model": model, "input": PROBE_INPUT}, "ollama-embed")
    add("Ollama native (old)", r + "/api/embeddings", {"model": model, "prompt": PROBE_INPUT[0]}, "ollama-prompt")
    return out


# A 4xx naming the model (rather than the route) is a *positive* signal: the
# embeddings endpoint exists and parsed the request, it just does not serve that
# model. Reporting it as "no embeddings here" sends the operator after the wrong
# fix — the route is fine, the model name or the host is not.
_UNKNOWN_MODEL_HINTS = ("unknown_model", "model not found", "does not exist",
                        "unknown model", "no such model", "invalid model")


def model_rejected(body):
    """True if a 4xx body indicates a working route rejecting the model name."""
    low = (body or "").lower()
    return any(h in low for h in _UNKNOWN_MODEL_HINTS)


def served_models(body):
    """Best-effort list of models the endpoint says it does serve."""
    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return []
    stack, out = [obj], []
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in ("known", "available", "models") and isinstance(v, list):
                    out += [m for m in v if isinstance(m, str)]
                else:
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def check_shape(parsed, shape):
    """Return (ok_for_align, dim, note). ok_for_align is what align.py needs."""
    if not isinstance(parsed, dict):
        return False, 0, "response is not a JSON object"
    if isinstance(parsed.get("data"), list) and parsed["data"]:
        row = parsed["data"][0]
        if isinstance(row, dict) and isinstance(row.get("embedding"), list):
            miss = "index" if "index" not in row else ""
            return True, len(row["embedding"]), ("no 'index' key (align.py sorts on it)"
                                                 if miss else "OpenAI shape — align.py compatible")
        return False, 0, "'data' present but no data[0].embedding"
    for k in ("embeddings", "embedding"):
        v = parsed.get(k)
        if isinstance(v, list) and v:
            dim = len(v[0]) if isinstance(v[0], list) else len(v)
            return False, dim, ("native '%s' shape — align.py expects data[].embedding "
                                "and would KeyError into difflib" % k)
    return False, 0, "no embedding field found (keys: %s)" % ", ".join(list(parsed)[:6])


def main():
    ap = argparse.ArgumentParser(description="Diagnose the embeddings endpoint used by align.py.")
    ap.add_argument("--base", default=None, help="override SAGE_EMBED_BASE_URL / SAGE_LLM_BASE_URL")
    ap.add_argument("--model", default=None, help="override SAGE_EMBED_MODEL")
    ap.add_argument("--end-to-end", action="store_true",
                    help="after probing, call align._embed() with the resolved config")
    a = ap.parse_args()

    # --- 1. resolve config exactly as align.py does -------------------------
    print("=" * 78)
    print("SAGE embeddings debug")
    print("=" * 78)
    ep = align.embed_endpoint()
    model = a.model or (ep or {}).get("model") or os.environ.get("SAGE_EMBED_MODEL")
    base = a.base or (ep or {}).get("base") or os.environ.get("SAGE_EMBED_BASE_URL") \
        or os.environ.get("SAGE_LLM_BASE_URL")
    key = (ep or {}).get("key") or os.environ.get("SAGE_EMBED_API_KEY",
                                                  os.environ.get("SAGE_LLM_API_KEY", ""))

    print("\n[1] RESOLVED CONFIG")
    print("    SAGE_EMBED_MODEL     %s" % (model or "(unset)"))
    print("    SAGE_EMBED_BASE_URL  %s" % (os.environ.get("SAGE_EMBED_BASE_URL") or "(unset)"))
    print("    SAGE_LLM_BASE_URL    %s" % (os.environ.get("SAGE_LLM_BASE_URL") or "(unset)"))
    print("    effective base       %s" % (base or "(none)"))
    print("    api key              %s" % ("<redacted, %d chars>" % len(key) if key else "(none)"))
    overridden = bool(a.base or a.model)
    if ep is None and not overridden:
        print("\n    align.embed_endpoint() returned None -> align.py uses difflib WITHOUT")
        print("    any HTTP call. Note that is a *different* failure from the 405 you saw:")
        print("    a 405 means the endpoint WAS resolved and the POST was rejected.")
        if not os.environ.get("SAGE_EMBED_MODEL"):
            print("    Cause here: SAGE_EMBED_MODEL is unset (it is what enables the backend).")
    elif ep is None and overridden:
        print("\n    (env config alone would resolve to None -> difflib; probing with your")
        print("     --base/--model overrides instead)")
    if not base:
        sys.exit("\nno base url — set SAGE_EMBED_BASE_URL or SAGE_LLM_BASE_URL, or pass --base")
    if not model:
        model = "<unset>"
        print("\n    (probing with model=%r; the server will likely reject it — set" % model)
        print("     SAGE_EMBED_MODEL or pass --model to test properly)")

    print("\n    align.py would POST to: %s" % (base.rstrip("/") + "/embeddings"))

    # --- 2. is the host even right? -----------------------------------------
    print("\n[2] HOST REACHABILITY / SERVED MODELS")
    for label, url in (("OpenAI-compatible", _root(base) + "/v1/models"),
                       ("Ollama native", _root(base) + "/api/tags")):
        st, body, parsed = _get(url, key)
        print("    GET %-42s status %s" % (url, st))
        if st == 200 and parsed:
            items = parsed.get("data") or parsed.get("models") or []
            names = [i.get("id") or i.get("name") for i in items if isinstance(i, dict)]
            names = [n for n in names if n]
            print("        %d model(s): %s" % (len(names), ", ".join(names[:10])
                                               + (" …" if len(names) > 10 else "")))
            if model in names:
                print("        '%s' IS served here" % model)
            elif names:
                print("        '%s' NOT in this list — check the embed model name" % model)
        elif st:
            print("        %s" % body[:160].replace("\n", " "))
        else:
            print("        %s" % body[:160])

    # --- 3. probe every plausible route -------------------------------------
    print("\n[3] EMBEDDINGS ROUTE PROBE  (input: %d short strings)" % len(PROBE_INPUT))
    working, wrong_model = [], []
    for label, url, payload, shape in candidates(base, model):
        st, allow, body, parsed = _post(url, payload, key)
        print("\n    POST %s" % url)
        print("         (%s)  status %s" % (label, st))
        if 400 <= st < 500 and model_rejected(body):
            avail = served_models(body)
            print("         %s — ROUTE WORKS, but it does not serve '%s'" % (st, model))
            if avail:
                print("         it serves: %s" % ", ".join(avail[:10]))
            wrong_model.append((url, avail))
        elif st == 405:
            print("         405 Method Not Allowed — path exists but refuses POST")
            print("         Allow: %s" % (allow or "(header absent)"))
        elif st == 404:
            print("         404 — no such route here")
        elif st in (401, 403):
            print("         %s — auth rejected; check SAGE_EMBED_API_KEY" % st)
        elif st == 200:
            ok, dim, note = check_shape(parsed, shape)
            print("         200 OK — dim=%d  %s" % (dim, note))
            if ok:
                working.append((label, url, dim))
        elif st == 0:
            print("         network: %s" % body[:200])
        if st not in (200, 405) and body:
            print("         body: %s" % body[:200].replace("\n", " "))

    # --- 4. verdict ----------------------------------------------------------
    print("\n" + "=" * 78)
    print("SUMMARY")
    if working:
        label, url, dim = working[0]
        good_base = url[:-len("/embeddings")] if url.endswith("/embeddings") else url
        print("  Working OpenAI-shaped route: %s (dim=%d)" % (url, dim))
        print("  align.py appends '/embeddings', so export the base WITHOUT it:")
        print("\n      export SAGE_EMBED_BASE_URL=%s" % good_base)
        print("      export SAGE_EMBED_MODEL=%s" % model)
        print("\n  Then re-run alignment on the existing snapshot (no re-extraction):")
        print("      python3 -m pipeline.align --spec 'TS 38.331' --version 19.2.0")
    elif wrong_model:
        url, avail = wrong_model[0]
        good_base = url[:-len("/embeddings")] if url.endswith("/embeddings") else url
        print("  The embeddings ROUTE works — it rejected the model, not the request:")
        print("      %s" % url)
        print("  So this is a model/host problem, not a missing endpoint.")
        if avail:
            print("  Models served here: %s" % ", ".join(avail[:10]))
            print("  None of those is an embedding model, so either:")
        print("    (a) load an embedding model (e.g. bge-m3, nomic-embed-text) on that")
        print("        host and set SAGE_EMBED_MODEL to its exact served name; or")
        print("    (b) point SAGE_EMBED_BASE_URL at whichever host already serves one")
        print("        (it need not be the chat host — SAGE_EMBED_BASE_URL is separate).")
        print("  Once it resolves, re-run alignment only — no re-extraction:")
        print("      python3 -m pipeline.align --spec 'TS 38.331' --version 19.2.0")
        print("  Base to export when the model is available: %s" % good_base)
    else:
        print("  No route returned an OpenAI-shaped embedding.")
        print("  If every candidate 405s or 404s, this server does not serve embeddings")
        print("  at all (common for chat-only vLLM/llama.cpp deployments) — point")
        print("  SAGE_EMBED_BASE_URL at a host that does, or accept the difflib backend")
        print("  and note the ρ distribution is lexical-only when reporting results.")
    print("=" * 78)

    # --- 5. optional end-to-end through align.py itself ----------------------
    if a.end_to_end:
        print("\n[5] END-TO-END via align._embed()")

        def try_base(b, why):
            print("\n    %s: base=%s" % (why, b))
            try:
                vecs = align._embed({"base": b.rstrip("/"), "model": model, "key": key},
                                    PROBE_INPUT)
                print("    OK — %d vector(s), dim=%d" % (len(vecs), len(vecs[0]) if vecs else 0))
                print("    distance(%r, %r) = %.4f"
                      % (PROBE_INPUT[0], PROBE_INPUT[1],
                         align._cosine_distance(vecs[0], vecs[1])))
                print("    -> align.py WILL use the embedding backend with this base.")
                return True
            except Exception as exc:
                print("    FAILED (%s: %s)" % (type(exc).__name__, exc))
                print("    -> this is the exact exception align.suggest() swallows into difflib.")
                return False

        ok = try_base(base, "as currently configured")
        if working:
            win = working[0][1]
            good_base = win[:-len("/embeddings")] if win.endswith("/embeddings") else win
            if good_base.rstrip("/") != base.rstrip("/"):
                try_base(good_base, "with the recommended base")
        elif not ok:
            print("\n    No working route to retry — see SUMMARY above.")


if __name__ == "__main__":
    main()
