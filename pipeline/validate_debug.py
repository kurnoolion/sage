"""Validation debug — explain a snapshot's validation errors (D-008 invariants).

`pipeline.run` prints only a count and the first ten errors ("2360 errors, 191
warnings"), which is not enough to tell *why* a run went wrong. This tool reads
an existing ``snapshot.json`` and breaks the errors down by category, then — for
the category that usually dominates — works out whether the dangling relation
endpoints are **near-misses** (an id the merge step could have resolved) or
genuine hallucinations. That distinction decides the fix: id normalization in
the merge stage vs. prompt work on the extractor.

Usage:
    python3 -m pipeline.validate_debug --spec "TS 38.331" --version 19.2.0
                                       [--label L] [--top N] [--samples N]
                                       [--no-corpus] [--out FILE]

    --no-corpus  skip loading the corpus store. Safe: every corpus check in
                 validate.py produces a *warning*, never an error, so the error
                 analysis is identical — only the warning total is withheld.
    --top N      rows per ranked table (default 12)
    --samples N  example ids shown per row (default 2)

The analysis re-derives validate.py's error rules in structured form (so results
can be grouped and counted) and then **reconciles** its total against a real
`validate.validate()` call. A mismatch is reported loudly — it means this tool
has drifted from the validator and its breakdown should not be trusted.

Output contains entity/relation ids, types and short labels — no clause prose —
so it is safe to paste into a run report (cf. the D-012b caution on llm_debug
--clause, which does dump corpus text).
"""
import argparse
import collections
import json
import os
import re
import sys

from . import ids, ontology, snapshot

# ---------------------------------------------------------------------------
# Structured re-derivation of validate.py's error rules
# ---------------------------------------------------------------------------
# Category -> human blurb, in the order they are reported.
CATEGORIES = (
    ("entity-undeclared-type",   "entity type not in the ontology"),
    ("relation-undeclared-type", "relation type not in the ontology"),
    ("dangling-from",            "relation .from references a missing entity"),
    ("dangling-to",              "relation .to references a missing entity"),
    ("domain-violation",         "from-type outside the relation's domain"),
    ("range-violation",          "to-type outside the relation's range"),
    ("lifecycle-release",        "observed_in names an unknown release"),
    ("lifecycle-field",          "introduced_in/valid_until names an unknown release"),
    ("lifecycle-supersedes",     "supersedes points at an unknown id"),
)


# Types named in a relationship's domain/range that have no entity record by
# design. ontology.py calls Clause "a corpus pseudo-type (DEFINED_IN range) with
# no entity record" — but validate.py's `r["to"] not in by_id` check has no
# exemption for them, so every edge into a pseudo-type errors as "unknown
# entity" by construction. That is an ontology/validator gap, not bad extraction,
# and it must be reported separately or it swamps the real findings.
PSEUDO_TYPES = frozenset(
    t for spec in ontology.RELATIONSHIP_TYPES.values()
    for t in list(spec["domain"]) + list(spec["range"])
    if t != "*" and t not in ontology.ENTITY_TYPES)


def pseudo_slot(rel_type, slot):
    """True if this relation's slot can *only* hold a pseudo-type (never an entity)."""
    spec = ontology.RELATIONSHIP_TYPES.get(rel_type)
    if not spec:
        return False
    allowed = set(spec["domain"] if slot == "from" else spec["range"])
    return bool(allowed) and allowed <= PSEUDO_TYPES


def analyze(entities, relations, version):
    """Return validate.py's errors as structured findings (same rules, same order).

    Mirrors ``validate.validate``; kept in lockstep by the reconciliation check
    in ``report()``. Corpus checks are omitted deliberately — they only ever
    yield warnings.
    """
    findings = []
    etypes, rtypes = ontology.ENTITY_TYPES, ontology.RELATIONSHIP_TYPES
    by_id = {e["id"]: e for e in entities}
    allids = set(by_id) | {r["id"] for r in relations}

    for e in entities:
        if e["type"] not in etypes:
            findings.append({"cat": "entity-undeclared-type", "id": e["id"],
                             "type": e["type"], "label": e.get("label", "")})

    for r in relations:
        if r["type"] not in rtypes:
            findings.append({"cat": "relation-undeclared-type", "id": r["id"], "type": r["type"]})
            continue
        spec = rtypes[r["type"]]
        if r["from"] not in by_id:
            findings.append({"cat": "dangling-from", "id": r["id"], "rel": r["type"],
                             "ref": r["from"], "slot": "from"})
        if r["to"] not in by_id:
            findings.append({"cat": "dangling-to", "id": r["id"], "rel": r["type"],
                             "ref": r["to"], "slot": "to"})
        ft = by_id.get(r["from"], {}).get("type")
        tt = by_id.get(r["to"], {}).get("type")
        if ft and not ontology.domain_range_ok(spec["domain"], ft):
            findings.append({"cat": "domain-violation", "id": r["id"], "rel": r["type"],
                             "got": ft, "allowed": spec["domain"], "ref": r["from"]})
        if tt and not ontology.domain_range_ok(spec["range"], tt):
            findings.append({"cat": "range-violation", "id": r["id"], "rel": r["type"],
                             "got": tt, "allowed": spec["range"], "ref": r["to"]})

    from .config import RELEASES
    relset = set(RELEASES)
    for obj, what in ([(e, "entity") for e in entities] + [(r, "relation") for r in relations]):
        for rid in obj.get("observed_in") or []:
            if rid not in relset:
                findings.append({"cat": "lifecycle-release", "id": obj["id"], "what": what, "got": rid})
        for f in ("introduced_in", "valid_until"):
            v = obj.get(f)
            if v is not None and v not in relset:
                findings.append({"cat": "lifecycle-field", "id": obj["id"], "what": what,
                                 "field": f, "got": v})
        if obj.get("supersedes") is not None and obj["supersedes"] not in allids:
            findings.append({"cat": "lifecycle-supersedes", "id": obj["id"], "what": what,
                             "got": obj["supersedes"]})
    return findings


# ---------------------------------------------------------------------------
# Near-miss resolution for dangling endpoints
# ---------------------------------------------------------------------------
_NONALNUM = re.compile(r"[^a-z0-9]+")

# Words an extractor may redundantly prefix onto a name it already typed, e.g.
# id ".../clause/Clause-5-5-4-26" for what should be ".../clause/5-5-4-26".
_TYPE_WORDS = frozenset(
    [t.lower() for t in ontology.ENTITY_TYPES] + list(ids.TYPE_SLUG.values()))
_LEADING_TYPE_WORD = re.compile(
    r"^(?:%s)[-_ ]+" % "|".join(sorted(map(re.escape, _TYPE_WORDS), key=len, reverse=True)),
    re.IGNORECASE)

# Valid id buckets: the "<type>" segment canonical_id() emits. Unknown types fall
# back to typ.lower(), so an invented type shows up here as a bogus bucket.
VALID_BUCKETS = frozenset(list(ids.TYPE_SLUG.values()) + ["concept", "release"])


def _norm(s):
    return _NONALNUM.sub("-", (s or "").lower()).strip("-")


def _name_of(eid):
    return eid.rsplit("/", 1)[-1] if "/" in eid else eid


def _bucket_of(eid):
    parts = eid.split("/")
    return parts[-2] if len(parts) >= 2 else "(none)"


def build_index(entities):
    """Lookup tables over real entity ids, for progressively looser matching."""
    idx = {"lower": {}, "norm": {}, "name": collections.defaultdict(list)}
    for e in entities:
        eid = e["id"]
        idx["lower"].setdefault(eid.lower(), eid)
        idx["norm"].setdefault(_norm(eid), eid)
        idx["name"][_norm(_LEADING_TYPE_WORD.sub("", _name_of(eid)))].append(eid)
    return idx


# Rules are tried in order; the first hit classifies the reference. Ordering is
# strictest-first so a match is attributed to the smallest discrepancy.
RESOLUTION_RULES = (
    ("pseudo-type-target", "target is a pseudo-type with no entity record BY DESIGN"),
    ("case-only",         "differs only by letter case"),
    ("separator",         "differs only in punctuation/separators"),
    ("type-word-prefix",  "name carries a redundant type word (Clause-5-3-3 vs 5-3-3)"),
    ("wrong-type-bucket", "same name, filed under a different/invented type"),
    ("UNRESOLVED",        "no entity resembles this id — likely hallucinated"),
)


def resolve(ref, idx):
    """Classify a dangling id. Returns (rule, matched_id_or_None)."""
    hit = idx["lower"].get(ref.lower())
    if hit and hit != ref:
        return "case-only", hit
    hit = idx["norm"].get(_norm(ref))
    if hit and hit != ref:
        return "separator", hit

    bare = _LEADING_TYPE_WORD.sub("", _name_of(ref))
    key = _norm(bare)
    cands = idx["name"].get(key) or []
    if cands:
        # Same bucket => the only difference was the redundant type word.
        same_bucket = [c for c in cands if _bucket_of(c) == _bucket_of(ref)]
        if same_bucket and bare != _name_of(ref):
            return "type-word-prefix", same_bucket[0]
        return "wrong-type-bucket", cands[0]
    return "UNRESOLVED", None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def detect_reversed(entities, relations):
    """Relations whose endpoints satisfy the declared domain/range *swapped*.

    A reversed edge fails BOTH slot checks, so it shows up twice in the error
    count — once as a domain violation, once as a range violation. Naming them
    separately keeps that double-count from reading as twice as many defects,
    and points at a single fix (edge direction) rather than two.
    """
    by_id = {e["id"]: e for e in entities}
    out = collections.Counter()
    for r in relations:
        spec = ontology.RELATIONSHIP_TYPES.get(r["type"])
        if not spec:
            continue
        ft = by_id.get(r["from"], {}).get("type")
        tt = by_id.get(r["to"], {}).get("type")
        if not ft or not tt:
            continue
        wrong = (not ontology.domain_range_ok(spec["domain"], ft)
                 and not ontology.domain_range_ok(spec["range"], tt))
        swapped = (ontology.domain_range_ok(spec["domain"], tt)
                   and ontology.domain_range_ok(spec["range"], ft))
        if wrong and swapped:
            out[r["type"]] += 1
    return out


def _bar(n, total):
    return "%5d %5.1f%%" % (n, 100.0 * n / total if total else 0.0)


def _rank(counter, total, top, fmt=lambda k: k, extra=None):
    lines = []
    for k, n in counter.most_common(top):
        line = "    %s  %s" % (_bar(n, total), fmt(k))
        if extra:
            ex = extra(k)
            if ex:
                line += "\n%s" % ex
        lines.append(line)
    rest = len(counter) - top
    if rest > 0:
        lines.append("    %s  (+%d more distinct)" % (" " * 12, rest))
    return "\n".join(lines)


def report(snap, findings, errs_expected, warns_n, top, samples, out):
    ents, rels = snap["entities"], snap["relations"]
    p = lambda s="": print(s, file=out)

    p("=" * 78)
    p("SAGE validation debug — %s %s" % (snap.get("spec"), snap.get("version")))
    p("generated: %s   entities: %d   relations: %d"
      % (snap.get("generated"), len(ents), len(rels)))

    if errs_expected is None:
        p("errors: %d (validate.py not re-run)   warnings: not computed (--no-corpus)"
          % len(findings))
    else:
        ok = "OK" if errs_expected == len(findings) else "MISMATCH"
        p("errors: %d   warnings: %d   [reconciled with validate.py: %s]"
          % (len(findings), warns_n, ok))
        if errs_expected != len(findings):
            p("  !! validate.py reported %d errors but this tool derived %d — the"
              % (errs_expected, len(findings)))
            p("     breakdown below has drifted from validate.py and is UNRELIABLE.")
    total = len(findings) or 1
    p()

    p("ERRORS BY CATEGORY")
    by_cat = collections.Counter(f["cat"] for f in findings)
    for cat, blurb in CATEGORIES:
        if by_cat.get(cat):
            p("  %s  %-24s %s" % (_bar(by_cat[cat], total), cat, blurb))
    p()

    # --- [1] invented entity types -----------------------------------------
    bad_types = [f for f in findings if f["cat"] == "entity-undeclared-type"]
    if bad_types:
        c = collections.Counter(f["type"] for f in bad_types)
        ex = collections.defaultdict(list)
        for f in bad_types:
            ex[f["type"]].append("%s %r" % (f["id"], f["label"][:40]))
        p("[1] UNDECLARED ENTITY TYPES — %d entities across %d invented type(s)"
          % (len(bad_types), len(c)))
        p(_rank(c, len(bad_types), top,
                fmt=lambda k: k + ("   <- declared as a PSEUDO-type in a relation range"
                                   if k in PSEUDO_TYPES else "   <- genuinely invented"),
                extra=lambda k: "\n".join("             e.g. %s" % s for s in ex[k][:samples])))
        p("    -> these types are absent from ontology.ENTITY_TYPES; every relation")
        p("       touching them also fails domain/range below (collateral damage).")
        if set(c) & PSEUDO_TYPES:
            p("    -> the PSEUDO-type rows are the ontology gap, not extractor error: the")
            p("       extractor materialized an entity for a type the ontology names in a")
            p("       range but never declares. Either declare it in ENTITY_TYPES or stop")
            p("       emitting entities for it — the two halves must agree.")
        p()

    bad_rtypes = [f for f in findings if f["cat"] == "relation-undeclared-type"]
    if bad_rtypes:
        c = collections.Counter(f["type"] for f in bad_rtypes)
        p("[2] UNDECLARED RELATION TYPES — %d relations across %d invented type(s)"
          % (len(bad_rtypes), len(c)))
        p(_rank(c, len(bad_rtypes), top))
        p()

    # --- [3] dangling endpoints + near-miss analysis -------------------------
    dang = [f for f in findings if f["cat"] in ("dangling-from", "dangling-to")]
    if dang:
        refs = [f["ref"] for f in dang]
        distinct = sorted(set(refs))
        idx = build_index(ents)
        res = {r: resolve(r, idx) for r in distinct}

        p("[3] DANGLING RELATION ENDPOINTS — %d references -> %d distinct missing ids"
          % (len(dang), len(distinct)))
        p("    How closely does each missing id resemble a real one?")
        p("    (weighted by references, so the numbers add up to the error count)")
        wc = collections.Counter()
        # A pseudo-type slot is classified by the RELATION, not the id: no entity
        # is ever supposed to exist there, so id similarity is beside the point.
        rule_of, pseudo_rels = {}, collections.Counter()
        for f in dang:
            if pseudo_slot(f["rel"], f["slot"]):
                rule_of[id(f)] = "pseudo-type-target"
                pseudo_rels[f["rel"]] += 1
            else:
                rule_of[id(f)] = res[f["ref"]][0]
            wc[rule_of[id(f)]] += 1
        pseudo_refs = {f["ref"] for f in dang if rule_of[id(f)] == "pseudo-type-target"}
        for rule, blurb in RESOLUTION_RULES:
            if not wc.get(rule):
                continue
            p("    %s  %-18s %s" % (_bar(wc[rule], len(dang)), rule, blurb))
            if rule == "pseudo-type-target":
                for rel, n in pseudo_rels.most_common(top):
                    spec = ontology.RELATIONSHIP_TYPES[rel]
                    p("             %s (range %s) x%d" % (rel, spec["range"], n))
                for r in sorted(pseudo_refs)[:samples]:
                    p("             e.g. target id %s" % r)
                continue
            shown = [r for r in distinct
                     if r not in pseudo_refs and res[r][0] == rule][:samples]
            for r in shown:
                tgt = res[r][1]
                p("             %s" % r + ("  ->  %s" % tgt if tgt else ""))
        p()
        if wc.get("pseudo-type-target"):
            p("    !! %d of these are NOT extraction errors. ontology.py declares those"
              % wc["pseudo-type-target"])
            p("       range types as pseudo-types with no entity record, but validate.py's")
            p("       'to/from unknown entity' check has no exemption for them — so they")
            p("       error by construction. Fix the validator, not the extractor.")
            p("       Pseudo-types in this ontology: %s" % ", ".join(sorted(PSEUDO_TYPES)))
            p()
        p("    Missing ids by type bucket ('*' = not a declared type slug):")
        bc = collections.Counter(_bucket_of(f["ref"]) for f in dang)
        p(_rank(bc, len(dang), top,
                fmt=lambda k: "/%s/%s" % (k, "" if k in VALID_BUCKETS else "   *invented type")))
        p()
        nearmiss = sum(n for r, n in wc.items()
                       if r not in ("UNRESOLVED", "pseudo-type-target"))
        p("    => %d validator-gap (fix validate.py), %d near-miss ids (fix id"
          % (wc.get("pseudo-type-target", 0), nearmiss))
        p("       normalization at merge), %d unresolved (fix the extractor/prompt)."
          % wc.get("UNRESOLVED", 0))
        p()

    # --- [4] domain/range ----------------------------------------------------
    dr = [f for f in findings if f["cat"] in ("domain-violation", "range-violation")]
    if dr:
        by_id_type = {e["id"]: e["type"] for e in ents}
        undeclared = {e["id"] for e in ents if e["type"] not in ontology.ENTITY_TYPES}
        collateral = sum(1 for f in dr if f["ref"] in undeclared)
        c = collections.Counter(
            "%s %s: %s not in %s" % (f["rel"], "from" if f["cat"] == "domain-violation" else "to",
                                     f["got"], f["allowed"]) for f in dr)
        # One miswired relation can fail both slots, so errors > defective edges.
        distinct_rels = len({f["id"] for f in dr})
        p("[4] DOMAIN / RANGE VIOLATIONS — %d errors across %d distinct relation(s)"
          % (len(dr), distinct_rels))
        if distinct_rels < len(dr):
            p("    (%d relations fail BOTH slots, so they are counted twice above)"
              % (len(dr) - distinct_rels))
        p(_rank(c, len(dr), top))

        rev = detect_reversed(ents, rels)
        if rev:
            tot = sum(rev.values())
            p("")
            p("    REVERSED EDGES — %d relation(s) whose endpoints fit the declared"
              % tot)
            p("    domain/range EXACTLY, but swapped. One fix (direction), not two:")
            for rtype, n in rev.most_common(top):
                spec = ontology.RELATIONSHIP_TYPES[rtype]
                p("      %5d  %s: emitted %s->%s, declared %s->%s"
                  % (n, rtype, spec["range"], spec["domain"], spec["domain"], spec["range"]))
            p("    -> these account for %d of the %d errors in this section." % (tot * 2, len(dr)))
            p("       Either the prompt must pin edge direction, or the ontology")
            p("       needs the inverse edge declared.")
        if collateral:
            p("    of which %d (%.1f%%) involve an entity of an UNDECLARED type —"
              % (collateral, 100.0 * collateral / len(dr)))
            p("    i.e. collateral damage from section [1], fixed by fixing the types.")
        p()

    # --- [5] lifecycle -------------------------------------------------------
    lc = [f for f in findings if f["cat"].startswith("lifecycle-")]
    if lc:
        c = collections.Counter("%s %s" % (f["cat"], f.get("got")) for f in lc)
        p("[5] LIFECYCLE FIELDS — %d" % len(lc))
        p(_rank(c, len(lc), top))
        p()

    p("=" * 78)


def main():
    ap = argparse.ArgumentParser(
        description="Break down a snapshot's validation errors by category and cause.")
    ap.add_argument("--spec", default="TS 38.331")
    ap.add_argument("--version", default="19.2.0")
    ap.add_argument("--label", default=None)
    ap.add_argument("--snapshot", default=None,
                    help="path to a snapshot.json (overrides --spec/--version/--label)")
    ap.add_argument("--top", type=int, default=12, help="rows per ranked table (default 12)")
    ap.add_argument("--samples", type=int, default=2, help="examples per row (default 2)")
    ap.add_argument("--no-corpus", action="store_true",
                    help="skip the corpus load (errors are unaffected; warnings withheld)")
    ap.add_argument("--out", default=None, help="write the report to a file instead of stdout")
    a = ap.parse_args()

    path = a.snapshot or os.path.join(
        snapshot.dir_for(a.spec, a.version, a.label), "snapshot.json")
    if not os.path.exists(path):
        sys.exit("no snapshot at %s — run the pipeline first, or pass --snapshot" % path)
    with open(path) as f:
        snap = json.load(f)

    findings = analyze(snap["entities"], snap["relations"], snap.get("version") or a.version)

    # Reconcile against the real validator so a drifted breakdown can't mislead.
    errs_expected, warns_n = None, 0
    if not a.no_corpus:
        try:
            from . import config, corpus, validate
            cfg = config.get(snap.get("spec") or a.spec, snap.get("version") or a.version)
            cps = corpus.Corpus(cfg.store_dir)
            errs, warns = validate.validate(snap["entities"], snap["relations"], cps, cfg.version)
            errs_expected, warns_n = len(errs), len(warns)
        except Exception as exc:
            print("note: corpus unavailable (%s: %s) — reporting errors only"
                  % (type(exc).__name__, exc), file=sys.stderr)

    out = open(a.out, "w") if a.out else sys.stdout
    try:
        report(snap, findings, errs_expected, warns_n, a.top, a.samples, out)
    finally:
        if a.out:
            out.close()
            print("report -> %s" % a.out)


if __name__ == "__main__":
    main()
