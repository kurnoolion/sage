"""Model-agnostic LLM extractor (D-010 pipeline stage 3).

Talks to any **OpenAI-compatible** chat-completions endpoint (Ollama, vLLM, …)
configured purely via env — no SDK dependency (stdlib urllib only):

    SAGE_LLM_BASE_URL   e.g. http://localhost:11434/v1   (Ollama) or http://gpu:8000/v1 (vLLM)
    SAGE_LLM_MODEL      e.g. qwen2.5:32b-instruct
    SAGE_LLM_API_KEY    optional (vLLM/openai); ignored by Ollama

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
import os
import urllib.request

from . import ids, ontology, records


def endpoint():
    base = os.environ.get("SAGE_LLM_BASE_URL")
    if not base:
        return None
    return {"base": base.rstrip("/"),
            "model": os.environ.get("SAGE_LLM_MODEL", "qwen2.5:32b-instruct"),
            "key": os.environ.get("SAGE_LLM_API_KEY", "")}


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


def _call(ep, messages, timeout=120):
    body = json.dumps({"model": ep["model"], "messages": messages,
                       "temperature": 0, "stream": False}).encode()
    req = urllib.request.Request(ep["base"] + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + ep["key"]})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.load(resp)
    return out["choices"][0]["message"]["content"]


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
    facts = _parse(_call(ep, messages))
    ents, rels = {}, []
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
            continue                       # malformed fact -> dropped (review covers gaps)
    return list(ents.values()), rels
