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
import shutil
import tempfile
import unittest

from . import align, config, embed_debug, llm, llm_cache, migrate, ontology, snapshot, validate, validate_debug
from .compare import _object_divergence
from .error_codes import PipelineError
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

    def test_explicit_arg_wins_over_env(self):
        # the --max-tokens flow: an explicit int arg overrides the env var
        os.environ["SAGE_LLM_BASE_URL"] = "http://x/v1"
        os.environ["SAGE_LLM_MAX_TOKENS"] = "512"
        try:
            self.assertEqual(llm.endpoint(max_tokens=4096)["max_tokens"], 4096)
        finally:
            del os.environ["SAGE_LLM_BASE_URL"], os.environ["SAGE_LLM_MAX_TOKENS"]


class TestRetry(unittest.TestCase):
    """_call retries transient endpoint failures, not terminal ones."""

    @staticmethod
    def _http(status):
        return PipelineError("LLM-E002", {"status": status, "reason": "x", "clause": "c", "body": ""})

    def test_is_transient(self):
        self.assertTrue(llm._is_transient(PipelineError("LLM-E003", {"clause": "c", "reason": "down"})))
        self.assertTrue(llm._is_transient(self._http(500)))
        self.assertTrue(llm._is_transient(self._http(503)))
        self.assertTrue(llm._is_transient(self._http(429)))
        self.assertFalse(llm._is_transient(self._http(400)))          # client error
        self.assertFalse(llm._is_transient(self._http(404)))
        self.assertFalse(llm._is_transient(PipelineError("LLM-E001", {"secs": 1, "limit": 1, "clause": "c"})))
        self.assertFalse(llm._is_transient(PipelineError("LLM-E004", {"clause": "c", "body": ""})))

    def test_backoff_grows_and_caps(self):
        self.assertEqual([llm._backoff_secs(n) for n in (1, 2, 3, 4)], [2.0, 4.0, 8.0, 16.0])
        self.assertEqual(llm._backoff_secs(10), 30.0)                 # capped

    def test_retries_env(self):
        self.assertEqual(llm._retries(), 3)
        os.environ["SAGE_LLM_RETRIES"] = "5"
        try:
            self.assertEqual(llm._retries(), 5)
        finally:
            del os.environ["SAGE_LLM_RETRIES"]

    def test_retries_transient_then_succeeds(self):
        n = {"c": 0}
        def flaky(ep, messages, clause_key=""):
            n["c"] += 1
            if n["c"] < 3:
                raise self._http(503)
            return "ok"
        real_once, real_sleep = llm._call_once, llm.time.sleep
        llm._call_once, llm.time.sleep = flaky, lambda s: None
        try:
            self.assertEqual(llm._call({"retries": 3, "model": "m"}, [], "c"), "ok")
            self.assertEqual(n["c"], 3)
        finally:
            llm._call_once, llm.time.sleep = real_once, real_sleep

    def test_gives_up_after_retries(self):
        n = {"c": 0}
        def always(ep, messages, clause_key=""):
            n["c"] += 1
            raise PipelineError("LLM-E003", {"clause": clause_key, "reason": "down"})
        real_once, real_sleep = llm._call_once, llm.time.sleep
        llm._call_once, llm.time.sleep = always, lambda s: None
        try:
            with self.assertRaises(PipelineError):
                llm._call({"retries": 2, "model": "m"}, [], "c")
            self.assertEqual(n["c"], 3)                               # 1 try + 2 retries
        finally:
            llm._call_once, llm.time.sleep = real_once, real_sleep

    def test_terminal_error_not_retried(self):
        n = {"c": 0}
        def client_err(ep, messages, clause_key=""):
            n["c"] += 1
            raise self._http(400)
        real_once, real_sleep = llm._call_once, llm.time.sleep
        llm._call_once, llm.time.sleep = client_err, lambda s: None
        try:
            with self.assertRaises(PipelineError):
                llm._call({"retries": 3, "model": "m"}, [], "c")
            self.assertEqual(n["c"], 1)                               # no retry on 4xx
        finally:
            llm._call_once, llm.time.sleep = real_once, real_sleep


class TestLLMCache(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _hdr(self, model="m", variant="v1"):
        return llm_cache.build_header("TS 38.331", "19.2.0", model, variant, 6000, False)

    def test_absent_cache(self):
        self.assertEqual(llm_cache.read(self.d), (None, {}))

    def test_write_read_roundtrip(self):
        h = self._hdr()
        with llm_cache.Writer(self.d, h) as w:
            w.add("5.1", [{"id": "e1"}], [{"id": "r1"}])
            w.add("5.2", [], [])                                      # zero-fact clause
        header, done = llm_cache.read(self.d)
        self.assertEqual(header, h)
        self.assertEqual(set(done), {"5.1", "5.2"})
        self.assertEqual(done["5.1"]["relations"], [{"id": "r1"}])
        self.assertEqual(done["5.2"]["entities"], [])                # recorded, not "missing"

    def test_resume_appends_single_header(self):
        h = self._hdr()
        with llm_cache.Writer(self.d, h) as w:
            w.add("5.1", [], [{"id": "r1"}])
        with llm_cache.Writer(self.d, h, resume=True) as w:
            w.add("5.2", [], [{"id": "r2"}])
        _, done = llm_cache.read(self.d)
        self.assertEqual(set(done), {"5.1", "5.2"})
        with open(llm_cache.cache_path(self.d)) as f:
            self.assertEqual(sum(1 for ln in f if "_header" in ln), 1)

    def test_fresh_write_truncates(self):
        h = self._hdr()
        with llm_cache.Writer(self.d, h) as w:
            w.add("5.1", [], [])
        with llm_cache.Writer(self.d, h) as w:                       # resume=False -> truncate
            w.add("5.9", [], [])
        _, done = llm_cache.read(self.d)
        self.assertEqual(set(done), {"5.9"})

    def test_header_mismatch_refused(self):
        with llm_cache.Writer(self.d, self._hdr(model="a")) as w:
            w.add("5.1", [], [])
        prev, _ = llm_cache.read(self.d)
        with self.assertRaises(llm_cache.HeaderMismatch):
            llm_cache.check_header(prev, self._hdr(model="b"))
        llm_cache.check_header(prev, self._hdr(model="a"))           # matching -> ok
        llm_cache.check_header(None, self._hdr())                    # no cache -> no-op

    def test_torn_final_line_skipped(self):
        h = self._hdr()
        with llm_cache.Writer(self.d, h) as w:
            w.add("5.1", [], [{"id": "r1"}])
        with open(llm_cache.cache_path(self.d), "a") as f:
            f.write('{"clause": "5.2", "entiti')                     # crash mid-write, no newline
        header, done = llm_cache.read(self.d)
        self.assertEqual((header, set(done)), (h, {"5.1"}))


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


class _NoCorpus:
    """Corpus stand-in for validator tests: every corpus check in validate.py
    emits warnings only, so errors are identical with or without a real store."""
    version = "19.2.0"

    def __contains__(self, clause):
        return False

    def haystack(self, clause):
        return ""


def _dbg_fixture():
    """Entities/relations exercising every error rule validate_debug classifies."""
    e = lambda i, t, l: {"id": i, "type": t, "label": l, "extractor": "llm", "defined_in": []}
    r = lambda i, f, t, ty: {"id": i, "from": f, "to": t, "type": ty, "provenance": []}
    ents = [
        e("3gpp:rrc/procedure/rrc-reconfiguration", "Procedure", "RRC reconfiguration"),
        e("3gpp:rrc/message/rrcreconfiguration", "Message", "RRCReconfiguration"),
        e("3gpp:rrc/timer/t310", "Timer", "T310"),
        e("3gpp:rrc/ie/spcellconfig", "InformationElement", "spCellConfig"),
        e("3gpp:rrc/clause/5-3-3-5", "Clause", "5.3.3.5"),        # pseudo-type materialized
        e("3gpp:rrc/constant/N310", "Constant", "N310"),          # genuinely invented
    ]
    rels = [
        r("r1", "3gpp:rrc/procedure/rrc-reconfiguration", "3gpp:rrc/clause/5-3-5-3", "DEFINED_IN"),
        r("r3", "3gpp:rrc/procedure/RRC-Reconfiguration", "3gpp:rrc/timer/t310", "STARTS"),
        r("r4", "3gpp:rrc/procedure/rrc_reconfiguration", "3gpp:rrc/timer/t310", "STOPS"),
        r("r5", "3gpp:rrc/message/Message-rrcreconfiguration",
          "3gpp:rrc/ie/spcellconfig", "CONTAINS"),
        r("r6", "3gpp:rrc/procedure/spcellconfig",
          "3gpp:rrc/message/rrcreconfiguration", "EXCHANGES"),
        r("r7", "3gpp:rrc/procedure/made-up-xyz", "3gpp:rrc/timer/t310", "STARTS"),
        r("r8", "3gpp:rrc/timer/t310", "3gpp:rrc/message/rrcreconfiguration", "EXCHANGES"),
        # range violation: STARTS ranges over Timer, not Message
        r("r9", "3gpp:rrc/procedure/rrc-reconfiguration",
          "3gpp:rrc/message/rrcreconfiguration", "STARTS"),
        # undeclared relation type — validate.py reports it and skips this relation
        r("r10", "3gpp:rrc/timer/t310", "3gpp:rrc/timer/t310", "INVENTED_REL"),
    ]
    ents[2]["observed_in"] = ["Rel-999"]          # lifecycle-release
    ents[3]["introduced_in"] = "Rel-999"          # lifecycle-field
    rels[0]["supersedes"] = "3gpp:rrc/nope/gone"  # lifecycle-supersedes
    return ents, rels


class TestValidateDebug(unittest.TestCase):
    def test_reconciles_with_validator(self):
        """The whole tool is only trustworthy if its structured findings match
        validate.py one-for-one — this is the guard against silent drift."""
        ents, rels = _dbg_fixture()
        errs, _ = validate.validate(ents, rels, _NoCorpus(), "19.2.0")
        findings = validate_debug.analyze(ents, rels, "19.2.0")
        self.assertEqual(len(findings), len(errs))

    def test_pseudo_types_discovered(self):
        # Clause is a DEFINED_IN range type with no ENTITY_TYPES declaration.
        self.assertIn("Clause", validate_debug.PSEUDO_TYPES)
        self.assertNotIn("Timer", validate_debug.PSEUDO_TYPES)
        self.assertTrue(validate_debug.pseudo_slot("DEFINED_IN", "to"))
        self.assertFalse(validate_debug.pseudo_slot("DEFINED_IN", "from"))  # domain is ["*"]
        self.assertFalse(validate_debug.pseudo_slot("STARTS", "to"))

    def test_resolution_rules(self):
        ents, _ = _dbg_fixture()
        idx = validate_debug.build_index(ents)
        cases = [
            ("3gpp:rrc/procedure/RRC-Reconfiguration", "case-only"),
            ("3gpp:rrc/procedure/rrc_reconfiguration", "separator"),
            ("3gpp:rrc/message/Message-rrcreconfiguration", "type-word-prefix"),
            ("3gpp:rrc/procedure/spcellconfig", "wrong-type-bucket"),
            ("3gpp:rrc/procedure/made-up-xyz", "UNRESOLVED"),
        ]
        for ref, expected in cases:
            rule, target = validate_debug.resolve(ref, idx)
            self.assertEqual(rule, expected, "%s -> %s" % (ref, rule))
            if expected == "UNRESOLVED":
                self.assertIsNone(target)
            else:
                self.assertIsNotNone(target)

    def test_reversed_edges_detected(self):
        """A reversed edge fails both slots, so it is counted twice in the error
        total — it must be named as one direction fault, not two defects."""
        e = lambda i, t: {"id": i, "type": t, "label": t, "extractor": "llm"}
        r = lambda i, f, t, ty: {"id": i, "from": f, "to": t, "type": ty}
        ents = [e("p", "Procedure"), e("ev", "Event"), e("ie", "InformationElement")]
        # TRIGGERS is declared Event->Procedure; emit it backwards.
        rels = [r("x1", "p", "ev", "TRIGGERS"),
                r("x2", "p", "ie", "WRITES")]      # wrong range, but NOT reversed
        rev = validate_debug.detect_reversed(ents, rels)
        self.assertEqual(rev["TRIGGERS"], 1)
        self.assertNotIn("WRITES", rev)

    def test_bucket_classification(self):
        self.assertEqual(validate_debug._bucket_of("3gpp:rrc/clause/5-3-3-5"), "clause")
        self.assertIn("timer", validate_debug.VALID_BUCKETS)
        self.assertNotIn("clause", validate_debug.VALID_BUCKETS)   # invented type slug


class TestEmbedDebug(unittest.TestCase):
    def test_shape_openai_accepted(self):
        ok, dim, _ = embed_debug.check_shape(
            {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}, "openai")
        self.assertTrue(ok)
        self.assertEqual(dim, 3)

    def test_shape_ollama_native_rejected(self):
        """200 OK but the wrong shape is the silent-failure case: align._embed
        raises KeyError and suggest() swallows it into difflib."""
        ok, _, note = embed_debug.check_shape({"embeddings": [[0.1, 0.2]]}, "ollama-embed")
        self.assertFalse(ok)
        self.assertIn("difflib", note)

    def test_shape_garbage_rejected(self):
        ok, _, _ = embed_debug.check_shape({"result": "nope"}, "openai")
        self.assertFalse(ok)

    def test_unknown_model_is_a_working_route(self):
        """A 4xx naming the MODEL means the route works — reporting it as 'no
        embeddings endpoint' sends the operator after the wrong fix."""
        body = ('{"detail":{"error":"unknown_model","requested":"bge-m3",'
                '"known":["chat-model-a","chat-model-b"]}}')
        self.assertTrue(embed_debug.model_rejected(body))
        self.assertEqual(embed_debug.served_models(body), ["chat-model-a", "chat-model-b"])

    def test_route_errors_are_not_model_errors(self):
        self.assertFalse(embed_debug.model_rejected('{"detail":"Not authenticated"}'))
        self.assertFalse(embed_debug.model_rejected("method not allowed"))
        self.assertEqual(embed_debug.served_models("<!doctype html>"), [])

    def test_root_strips_v1(self):
        self.assertEqual(embed_debug._root("http://h:8000/v1"), "http://h:8000")
        self.assertEqual(embed_debug._root("http://h:8000/v1/"), "http://h:8000")
        self.assertEqual(embed_debug._root("http://h:8000"), "http://h:8000")

    def test_candidates_probe_align_route_first_and_dedup(self):
        cands = embed_debug.candidates("http://h:8000/v1", "m")
        urls = [c[1] for c in cands]
        self.assertEqual(urls[0], "http://h:8000/v1/embeddings")   # what align.py uses
        self.assertEqual(len(urls), len(set(urls)))                # no duplicate probes
        self.assertIn("http://h:8000/api/embed", urls)


class TestReadsWritesRange(unittest.TestCase):
    """Pins the 2026-07-19 D-015 widening (see ontology.py comment). The full
    38.331 run produced 609 range violations — 28% of its errors — from
    procedures reading/writing IE fields under a UEVariable-only range."""

    def test_admits_both_variable_and_ie(self):
        for rel in ("READS", "WRITES"):
            rng = ontology.RELATIONSHIP_TYPES[rel]["range"]
            self.assertTrue(ontology.domain_range_ok(rng, "UEVariable"), rel)
            self.assertTrue(ontology.domain_range_ok(rng, "InformationElement"), rel)

    def test_widening_is_not_a_free_for_all(self):
        """Additive, not permissive: unrelated types are still rejected."""
        rng = ontology.RELATIONSHIP_TYPES["WRITES"]["range"]
        for typ in ("Timer", "Procedure", "Message", "State"):
            self.assertFalse(ontology.domain_range_ok(rng, typ), typ)

    def test_ie_subtypes_ride_along(self):
        """Subtype-aware, so IMS SIPHeader/Identity are admitted too — intended:
        a procedure setting a P-Access-Network-Info header is the same act."""
        rng = ontology.RELATIONSHIP_TYPES["WRITES"]["range"]
        for typ in ("SIPHeader", "Identity"):
            self.assertTrue(ontology.domain_range_ok(rng, typ), typ)


class TestRaisesDirection(unittest.TestCase):
    """TS 38.331 runs both ways round — 5.3.10.3's detection procedure RAISES
    radio link failure, and 5.3.7.2's radio link failure TRIGGERS
    re-establishment. Both must stay declared and distinct, or cause and effect
    become indistinguishable."""

    def test_both_directions_declared(self):
        self.assertEqual(ontology.RELATIONSHIP_TYPES["TRIGGERS"]["domain"], ["Event"])
        self.assertEqual(ontology.RELATIONSHIP_TYPES["TRIGGERS"]["range"], ["Procedure"])
        self.assertEqual(ontology.RELATIONSHIP_TYPES["RAISES"]["domain"], ["Procedure"])
        self.assertEqual(ontology.RELATIONSHIP_TYPES["RAISES"]["range"], ["Event"])

    def test_each_direction_validates_under_its_own_type(self):
        rng, dom = ontology.RELATIONSHIP_TYPES["RAISES"], ontology.RELATIONSHIP_TYPES["TRIGGERS"]
        self.assertTrue(ontology.domain_range_ok(rng["domain"], "Procedure"))
        self.assertTrue(ontology.domain_range_ok(rng["range"], "Event"))
        self.assertTrue(ontology.domain_range_ok(dom["domain"], "Event"))
        self.assertTrue(ontology.domain_range_ok(dom["range"], "Procedure"))

    def test_gold_seeds_one_example_of_each(self):
        with open(os.path.join(_ROOT, "pipeline", "gold", "TS38331.json")) as f:
            gold = json.load(f)
        rels = [f_["rel"] for e in gold["examples"] for f_ in e["facts"]]
        self.assertIn("RAISES", rels)
        self.assertIn("TRIGGERS", rels)


class TestMigrate(unittest.TestCase):
    def _snap(self):
        e = lambda i, t, l: {"id": i, "type": t, "label": l, "extractor": "llm"}
        r = lambda i, f, t, ty: {"id": i, "from": f, "to": t, "type": ty, "provenance": []}
        ents = [e("det", "Procedure", "detect"), e("ev", "Event", "rlf"),
                e("re", "Procedure", "reest")]
        rels = [r("m1", "det", "ev", "TRIGGERS"),    # Procedure->Event: retype
                r("m2", "ev", "re", "TRIGGERS")]     # Event->Procedure: leave alone
        return ents, rels

    def test_retypes_only_the_wrong_shape(self):
        ents, rels = self._snap()
        todo = migrate.plan(ents, rels)
        self.assertEqual(len(todo), 1)
        rel, new = todo[0]
        self.assertEqual(rel["id"], "m1")
        self.assertEqual(new, "RAISES")

    def test_correct_edges_are_never_touched(self):
        ents, rels = self._snap()
        touched = {r["id"] for r, _ in migrate.plan(ents, rels)}
        self.assertNotIn("m2", touched)

    def test_plan_is_idempotent(self):
        """Re-running after a migration must find nothing left to do."""
        ents, rels = self._snap()
        for rel, new in migrate.plan(ents, rels):
            rel["type"] = new
        self.assertEqual(migrate.plan(ents, rels), [])


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
