"""Stable, prefixed error codes for the SAGE pipeline.

Adopts NORA's D-012(a) convention (see docs/compact/DECISIONS.md D-017): every
pipeline failure carries a stable code ``{MODULE}-{SEVERITY}{NUMBER}`` so that
chat-mediated debugging has a stable surface, and so logs can name a failure
precisely without ever carrying corpus prose (the no-internal-content invariant,
D-012(b)). Format mirrors NORA's core/src/pipeline/error_codes.py.

  MODULE   : LLM (stage-3 extractor). More modules adopt codes as they need them.
  SEVERITY : E=error, W=warning
  NUMBER   : 3-digit

Usage:
    from .error_codes import PipelineError
    raise PipelineError("LLM-E001", {"clause": key, "secs": 130, "limit": 120})
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDef:
    code: str
    message: str
    hint: str

    def format(self, **kw):
        msg = self.message
        for k, v in kw.items():
            msg = msg.replace("{%s}" % k, str(v))
        return "[%s] %s" % (self.code, msg)


class PipelineError(RuntimeError):
    """A pipeline failure carrying a stable error code + remediation hint.

    ``str(err)`` is ``[CODE] message | hint: …`` so the code surfaces in logs,
    tracebacks, and the chat-mediated debugging surface alike. ``.code`` /
    ``.context`` / ``.hint`` are available for structured handling.
    """

    def __init__(self, code, context=None):
        self.code = code
        self.context = context or {}
        defn = CODES.get(code)
        if defn:
            self.message = defn.format(**self.context)
            self.hint = defn.hint
        else:
            self.message = "[%s] unknown error" % code
            self.hint = ""
        super().__init__("%s | hint: %s" % (self.message, self.hint) if self.hint
                         else self.message)


# --- catalog --------------------------------------------------------------
_DEFS = [
    # LLM extractor (stage 3)
    ErrorDef("LLM-E001", "LLM timeout after {secs}s (limit {limit}s) on clause {clause}",
             "raise SAGE_LLM_TIMEOUT — big clauses on a local model can exceed the 300s "
             "default; or reduce GPU load / check the server"),
    ErrorDef("LLM-E002", "LLM HTTP {status} {reason} on clause {clause}: {body}",
             "check model name / base_url / auth; probe it: python3 -m pipeline.llm_debug --probe <base>"),
    ErrorDef("LLM-E003", "LLM network error on clause {clause}: {reason}",
             "endpoint unreachable — check URL, network, proxy/VPN, and that the server is up"),
    ErrorDef("LLM-E004", "LLM returned no choices on clause {clause}: {body}",
             "endpoint responded with an unexpected shape — verify it is OpenAI chat-completions compatible"),
]

CODES = {d.code: d for d in _DEFS}
