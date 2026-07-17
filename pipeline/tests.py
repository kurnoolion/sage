"""Pipeline test suite — stdlib unittest, zero dependencies.

    python3 -m pipeline.tests          # everything (corpus-dependent tests
                                       # auto-skip when no store is fetched)
    python3 -m pipeline.tests -v

Two layers:
  * pure-logic tests — always run (no corpus, no network, no LLM);
  * corpus smoke tests — run only when the named corpus store exists locally
    (rebuild with corpus/fetch_spec.py); they assert the invariants that must
    hold on any machine (0 validation errors, non-empty spine), not exact
    counts, so they survive config evolution.
"""
import json
import os
import unittest

from . import align, config, llm, ontology, snapshot
from .compare import _object_divergence
from .eval_gold import _norm

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ent(id_, typ, label, extractor):
    return {"id": id_, "type": typ, "label": label, "extractor": extractor}


def _rel(rid, typ, frm, to, conf="high", extractor="llm"):
    return {"id": rid, "type": typ, "from": frm, "to": to, "confidence": conf,
            "extractor": extractor, "provenance": [{"clause": "5.1", "anchor": "a"}]}


class TestLLMParse(unittest.TestCase):
    """_parse: list on success (incl. valid empty []), None when unparseable."""

    def test_valid(self):
        self.assertEqual(llm._parse("[]"), [])
        self.assertEqual(llm._parse('noise [{"a": 1}] noise'), [{"a": 1}])

    def test_unparseable(self):
        self.assertIsNone(llm._parse("no array here"))
        self.assertIsNone(llm._parse("[not json]"))
        self.assertIsNone(llm._parse('{"a": 1}'))       # non-list JSON
        # note: "[1, 2" (truncated) is NOT unparseable — salvage recovers [1, 2];
        # see TestParseSalvage.
        self.assertEqual(llm._parse("[1, 2"), [1, 2])


class TestReasoningStrip(unittest.TestCase):
    """_parse strips reasoning before bracket-bounded extraction (NORA-aligned).

    Inline <think>… blocks are ALWAYS stripped; the FINAL_ANSWER_MARKER sentinel
    is opt-in via SAGE_LLM_REASONING_SENTINEL for UNtagged reasoning.
    """

    def test_inline_think_always_stripped(self):
        # brackets inside the thinking must not be mistaken for the JSON array
        self.assertEqual(llm._parse('<think>see [T300] and [x]</think>[{"a": 1}]'),
                         [{"a": 1}])

    def test_all_tag_aliases(self):
        for tag in ("think", "thinking", "reason", "reasoning"):
            self.assertEqual(
                llm._parse("<%s>junk [z]</%s>[1, 2]" % (tag, tag)), [1, 2],
                "tag %r not stripped" % tag)

    def test_tag_with_attributes(self):
        self.assertEqual(
            llm._parse('<think type="internal">[x]</think>[3]'), [3])

    def test_case_insensitive(self):
        self.assertEqual(llm._parse("<THINK>[x]</THINK>[4]"), [4])

    def test_orphan_close_tag(self):
        # server dropped the opening tag: only </think> present
        self.assertEqual(llm._parse("reasoning about [foo]\n</think>\n[]"), [])

    def test_multiple_blocks(self):
        self.assertEqual(
            llm._parse('<think>a [1]</think>noise<think>b [2]</think>[{"k": 2}]'),
            [{"k": 2}])

    def test_thinking_only_is_unparseable(self):
        self.assertIsNone(llm._parse("<think>[T300] only, no answer</think>"))

    def test_sentinel_off_by_default(self):
        self.assertFalse(llm.reasoning_sentinel_enabled())
        # marker present but sentinel off -> not treated specially; the array
        # after it still parses via the bracket span
        self.assertEqual(
            llm._parse("prose ===FINAL_ANSWER=== [5]"), [5])

    def test_sentinel_on_strips_untagged_prefix(self):
        os.environ["SAGE_LLM_REASONING_SENTINEL"] = "1"
        try:
            self.assertTrue(llm.reasoning_sentinel_enabled())
            # untagged reasoning full of brackets, then marker, then the answer
            reply = "Let me think about [T300] and [foo].\n===FINAL_ANSWER===\n[6]"
            self.assertEqual(llm._parse(reply), [6])
        finally:
            del os.environ["SAGE_LLM_REASONING_SENTINEL"]

    def test_sentinel_enabled_truthy_values(self):
        for on in ("1", "true", "YES", "on"):
            os.environ["SAGE_LLM_REASONING_SENTINEL"] = on
            try:
                self.assertTrue(llm.reasoning_sentinel_enabled(), on)
            finally:
                del os.environ["SAGE_LLM_REASONING_SENTINEL"]
        for off in ("0", "false", "no", "off", ""):
            os.environ["SAGE_LLM_REASONING_SENTINEL"] = off
            try:
                self.assertFalse(llm.reasoning_sentinel_enabled(), off)
            finally:
                del os.environ["SAGE_LLM_REASONING_SENTINEL"]

    def test_prompt_carries_marker_in_lockstep(self):
        cfg = TestPromptVariants.Cfg
        clause = {"title": "t", "text": "x"}
        m_off = llm.build_messages(cfg, "5.1", clause, [])
        self.assertNotIn(llm.FINAL_ANSWER_MARKER, m_off[0]["content"])
        os.environ["SAGE_LLM_REASONING_SENTINEL"] = "1"
        try:
            m_on = llm.build_messages(cfg, "5.1", clause, [])
            self.assertIn(llm.FINAL_ANSWER_MARKER, m_on[0]["content"])
        finally:
            del os.environ["SAGE_LLM_REASONING_SENTINEL"]


class TestParseSalvage(unittest.TestCase):
    """_parse recovers complete leading objects from a truncated/unparseable array."""

    def test_complete_array_unaffected(self):
        self.assertEqual(llm._parse('[{"a": 1}, {"b": 2}]'), [{"a": 1}, {"b": 2}])

    def test_truncated_recovers_complete_objects(self):
        # generation cut off mid-third-object -> keep the two complete ones
        content = '[{"a": 1}, {"b": 2}, {"c":'
        self.assertEqual(llm._parse(content), [{"a": 1}, {"b": 2}])

    def test_bracket_in_string_not_mistaken_for_close(self):
        # the real failure: ']' inside an anchor (RFC 3329 [48]) is the only ']'
        # left in a truncated reply, so the bracket-bounded slice can't parse
        content = ('[{"anchor": "RFC 3329 [48] applies"}, '
                   '{"anchor": "also [50] here"}, {"anchor":')
        self.assertEqual(
            llm._parse(content),
            [{"anchor": "RFC 3329 [48] applies"}, {"anchor": "also [50] here"}])

    def test_trailing_prose_after_valid_array(self):
        self.assertEqual(llm._parse('[{"a": 1}] and that is my answer [ref]'),
                         [{"a": 1}])

    def test_sentinel_then_truncated_array(self):
        os.environ["SAGE_LLM_REASONING_SENTINEL"] = "1"
        try:
            content = '===FINAL_ANSWER===\n[{"a": 1}, {"b":'
            self.assertEqual(llm._parse(content), [{"a": 1}])
        finally:
            del os.environ["SAGE_LLM_REASONING_SENTINEL"]

    def test_nothing_salvageable_is_none(self):
        self.assertIsNone(llm._parse("[garbage without any json"))
        self.assertIsNone(llm._parse("[not json]"))


class TestMaxTokens(unittest.TestCase):
    def test_endpoint_reads_env(self):
        os.environ["SAGE_LLM_BASE_URL"] = "http://x/v1"
        os.environ["SAGE_LLM_MAX_TOKENS"] = "2048"
        try:
            self.assertEqual(llm.endpoint()["max_tokens"], 2048)
        finally:
            del os.environ["SAGE_LLM_BASE_URL"], os.environ["SAGE_LLM_MAX_TOKENS"]

    def test_absent_by_default(self):
        os.environ["SAGE_LLM_BASE_URL"] = "http://x/v1"
        try:
            self.assertNotIn("max_tokens", llm.endpoint())
        finally:
            del os.environ["SAGE_LLM_BASE_URL"]

    def test_non_int_ignored(self):
        os.environ["SAGE_LLM_BASE_URL"] = "http://x/v1"
        os.environ["SAGE_LLM_MAX_TOKENS"] = "lots"
        try:
            self.assertNotIn("max_tokens", llm.endpoint())
        finally:
            del os.environ["SAGE_LLM_BASE_URL"], os.environ["SAGE_LLM_MAX_TOKENS"]


class TestPromptVariants(unittest.TestCase):
    class Cfg:
        spec, version, release = "TS 24.229", "19.6.0", "Rel-19"

    def test_resolution(self):
        self.assertEqual(llm.prompt_variant(), "v1")
        self.assertEqual(llm.prompt_variant("v2"), "v2")
        self.assertEqual(llm.prompt_variant("bogus"), "v1")
        os.environ["SAGE_LLM_PROMPT_VARIANT"] = "v2"
        try:
            self.assertEqual(llm.prompt_variant(), "v2")
        finally:
            del os.environ["SAGE_LLM_PROMPT_VARIANT"]

    def test_messages(self):
        m1 = llm.build_messages(self.Cfg, "5.1", {"title": "t", "text": "x"}, [])
        m2 = llm.build_messages(self.Cfg, "5.1", {"title": "t", "text": "x"}, [], variant="v2")
        self.assertNotIn("PASS 1", m1[0]["content"])
        self.assertIn("PASS 1", m2[0]["content"])
        self.assertEqual(m1[1]["content"], m2[1]["content"])   # user msg identical


class TestChunking(unittest.TestCase):
    def test_verbatim_substrings(self):
        text = "\n".join("para %d %s" % (i, "x" * 40) for i in range(20))
        chunks = llm._chunk_text(text, 100)
        self.assertGreater(len(chunks), 1)
        for ch in chunks:
            self.assertIn(ch, text)                            # KG⊨corpus survives

    def test_hard_split_lossless(self):
        block = "word " * 100
        pieces = llm._hard_split(block, 30)
        self.assertEqual("".join(pieces), block)


class TestConflictGroups(unittest.TestCase):
    def test_functional_only(self):
        rels = [
            _rel("r1", "GOVERNS", "t/T300", "p/estab"),
            _rel("r2", "GOVERNS", "t/T300", "p/reestab"),      # functional conflict
            _rel("r3", "EXCHANGES", "p/reg", "m/REGISTER"),
            _rel("r4", "EXCHANGES", "p/reg", "m/INVITE"),      # multi-valued: fine
        ]
        groups = snapshot.conflict_groups(rels)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["type"], "GOVERNS")
        self.assertEqual(len(groups[0]["members"]), 2)
        q = snapshot.build_review_queue([], rels, [])
        self.assertEqual(q[0]["kind"], "conflict-group")

    def test_flag_declared_in_ontology(self):
        self.assertTrue(ontology.RELATIONSHIP_TYPES["GOVERNS"].get("functional"))
        self.assertFalse(ontology.RELATIONSHIP_TYPES["EXCHANGES"].get("functional"))


class TestObjectDivergence(unittest.TestCase):
    def test_divergence(self):
        a = {"x1": _rel("x1", "TRANSITIONS_TO", "p1", "s_connected")}
        b = {"x2": _rel("x2", "TRANSITIONS_TO", "p1", "s_idle")}
        div = _object_divergence(a, b)
        self.assertEqual(len(div), 1)
        self.assertEqual(div[0]["only_a"], ["s_connected"])
        self.assertEqual(div[0]["only_b"], ["s_idle"])

    def test_disjoint_subjects_ignored(self):
        a = {"x1": _rel("x1", "TRANSITIONS_TO", "p1", "s1")}
        b = {"x2": _rel("x2", "TRANSITIONS_TO", "p2", "s2")}
        self.assertEqual(_object_divergence(a, b), [])


class TestAlign(unittest.TestCase):
    ENTITIES = [
        _ent("det:msg/rrcreconfiguration", "Message", "RRCReconfiguration", "deterministic:vocab:Message"),
        _ent("det:timer/t300", "Timer", "T300", "deterministic:vocab:Timer"),
        _ent("llm:msg/x", "Message", "RRC reconfiguration message", "llm"),
        _ent("llm:timer/y", "Timer", "timer T300", "llm"),
        _ent("llm:state/z", "State", "Some novel state", "llm"),   # no State canonical
        _ent("llm:msg/far", "Message", "Zzz quux frobnication", "llm"),
    ]

    def test_difflib_path(self):
        sugg, backend = align.suggest(self.ENTITIES, rho_val=0.35)
        self.assertEqual(backend, "difflib")
        by = {s["surface_label"]: s for s in sugg}
        self.assertEqual(by["timer T300"]["proposal"], "merge")            # containment
        self.assertEqual(by["timer T300"]["canonical_label"], "T300")
        self.assertEqual(by["RRC reconfiguration message"]["proposal"], "merge")
        self.assertEqual(by["Zzz quux frobnication"]["proposal"], "new-entity")
        self.assertNotIn("Some novel state", by)       # no type-compatible canonical
        self.assertEqual(sugg, sorted(sugg, key=lambda s: s["distance"]))
        items = align.review_items(sugg)
        self.assertEqual(len(items), 2)                # only the merges

    def test_subtype_compatibility(self):
        sugg, _ = align.suggest([
            _ent("det:sip/register", "SIPMethod", "REGISTER", "deterministic:vocab:SIPMethod"),
            _ent("llm:msg/reg", "Message", "REGISTER request", "llm"),
        ], rho_val=0.35)
        self.assertEqual(len(sugg), 1)
        self.assertEqual(sugg[0]["proposal"], "merge")

    def test_no_surfaces_noop(self):
        sugg, backend = align.suggest([self.ENTITIES[0]])
        self.assertEqual((sugg, backend), ([], "n/a"))

    def test_endpoint_failure_falls_back(self):
        os.environ["SAGE_EMBED_MODEL"] = "fake"
        os.environ["SAGE_EMBED_BASE_URL"] = "http://127.0.0.1:1/v1"   # unreachable
        try:
            sugg, backend = align.suggest(self.ENTITIES, rho_val=0.35)
            self.assertEqual(backend, "difflib")
            self.assertTrue(sugg)
        finally:
            del os.environ["SAGE_EMBED_MODEL"], os.environ["SAGE_EMBED_BASE_URL"]

    def test_mocked_embedding_backend(self):
        real = align._embed
        align._embed = lambda ep, texts, batch=100: [
            [1.0, 0.0] if "t300" in t.lower() else [0.0, 1.0] for t in texts]
        os.environ["SAGE_EMBED_MODEL"] = "fake-model"
        os.environ["SAGE_EMBED_BASE_URL"] = "http://x/v1"
        try:
            sugg, backend = align.suggest(self.ENTITIES, rho_val=0.35)
            self.assertEqual(backend, "embedding:fake-model")
            by = {s["surface_label"]: s for s in sugg}
            self.assertEqual(by["timer T300"]["distance"], 0.0)
        finally:
            align._embed = real
            del os.environ["SAGE_EMBED_MODEL"], os.environ["SAGE_EMBED_BASE_URL"]


class TestEvalGoldNorm(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(_norm("RRC-connection-establishment"),
                         _norm("RRC connection  establishment"))
        self.assertEqual(_norm("  T300 "), "t300")


class TestGoldSeeds(unittest.TestCase):
    """Gold few-shot facts must conform to the ontology (types + rels declared)."""

    def _check(self, path):
        with open(path) as f:
            gold = json.load(f)
        for ex in gold["examples"]:
            for fact in ex["facts"]:
                self.assertIn(fact["subject_type"], ontology.ENTITY_TYPES)
                self.assertIn(fact["object_type"], ontology.ENTITY_TYPES)
                self.assertIn(fact["rel"], ontology.RELATIONSHIP_TYPES)
                self.assertIn(fact["anchor"], ex["text"],
                              "anchor must be a span of the example text")

    def test_all_gold_files(self):
        gold_dir = os.path.join(_ROOT, "pipeline", "gold")
        for name in sorted(os.listdir(gold_dir)):
            if name.endswith(".json"):
                self._check(os.path.join(gold_dir, name))


# ---------------------------------------------------------------------------
# Corpus smoke tests — skip when the store isn't fetched on this machine.
# ---------------------------------------------------------------------------
def _store(spec_compact, version):
    return os.path.join(_ROOT, "corpus", "store", "%s-%s" % (spec_compact, version))


class TestCorpusSmoke24229(unittest.TestCase):
    STORE = _store("24229", "19.6.0")

    @unittest.skipUnless(os.path.exists(_store("24229", "19.6.0")),
                         "TS 24.229 19.6.0 corpus not fetched")
    def test_deterministic_spine(self):
        from . import corpus, extractors, ue_filter, validate
        cfg = config.get("TS 24.229", "19.6.0")
        cps = corpus.Corpus(cfg.store_dir)
        ue_keys, report = ue_filter.select(cps, cfg)
        self.assertGreater(report["kept"], 50)
        ents, rels = extractors.extract(cps, cfg, ue_keys)
        self.assertGreater(len(ents), 50)
        errs, _ = validate.validate(ents, rels, cps, "19.6.0")
        self.assertEqual(errs, [])


class TestCorpusSmoke38331(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(_store("38331", "19.2.0")),
                         "TS 38.331 19.2.0 corpus not fetched")
    def test_deterministic_spine_and_gold_anchors(self):
        from . import corpus, extractors, ue_filter, validate
        cfg = config.get("TS 38.331", "19.2.0")
        cps = corpus.Corpus(cfg.store_dir)
        ue_keys, report = ue_filter.select(cps, cfg)
        self.assertGreater(report["kept"], 100)
        ents, rels = extractors.extract(cps, cfg, ue_keys)
        types = {e["type"] for e in ents}
        self.assertLessEqual({"Procedure", "Message", "Timer", "State"}, types)
        self.assertTrue(rels, "INVOKES cross-refs expected")
        errs, _ = validate.validate(ents, rels, cps, "19.2.0")
        self.assertEqual(errs, [])
        # gold anchors resolve against the real corpus, not just example text
        with open(os.path.join(_ROOT, "pipeline", "gold", "TS38331.json")) as f:
            gold = json.load(f)
        hay_cache = {}
        for ex in gold["examples"]:
            for fact in ex["facts"]:
                self.assertTrue(
                    validate._anchor_in(cps, ex["clause"], fact["anchor"], hay_cache),
                    "gold anchor not found in %s: %r" % (ex["clause"], fact["anchor"]))


if __name__ == "__main__":
    unittest.main()
