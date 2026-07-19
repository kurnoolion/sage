"""Snapshot migration — retype relations after an ontology change (D-015).

When the TBox gains a type that an earlier run could not express, the facts are
already in the snapshot under whatever type the extractor reached for. Re-running
extraction would fix them, but a full-spec run is hours of local inference, so
this applies the same correction to an existing snapshot.

Usage:
    python3 -m pipeline.migrate --spec "TS 38.331" --version 19.2.0        # dry run
    python3 -m pipeline.migrate --spec "TS 38.331" --version 19.2.0 --apply

**Dry-run by default** (D-015 propose-only): it prints every edge it would
retype, with the clause and verbatim anchor, and the resulting validation-error
delta. Nothing is written without ``--apply``, which also leaves a
``snapshot.json.bak`` beside the original.

Why review rather than trust: a rule matches on *shape* (relation type + endpoint
types), and shape cannot distinguish "the extractor meant the other relation"
from "the extractor stated this one backwards". The RAISES rule below is a case
in point — TS 38.331 genuinely runs both ways (a procedure raises radio link
failure in 5.3.10.3; that event triggers re-establishment in 5.3.7.2), so a
Procedure->Event edge is *probably* a RAISES the old TBox could not express, but
a reversed TRIGGERS would match identically. Read the anchors before applying.
"""
import argparse
import json
import os
import shutil
import sys

from . import ontology

# (relation, from-type, to-type) -> new relation. Kept explicit and small: each
# rule is a claim about what the extractor meant, and should be reviewable as one.
RULES = {
    # 2026-07-19: RAISES added to the TBox. Runs before it typed "procedure
    # declares an event" as TRIGGERS, which fails both slot checks.
    ("TRIGGERS", "Procedure", "Event"): "RAISES",
}


def plan(entities, relations, rules=None):
    """Return [(relation, new_type)] for every edge a rule matches."""
    rules = RULES if rules is None else rules
    by_id = {e["id"]: e for e in entities}
    out = []
    for r in relations:
        ft = by_id.get(r["from"], {}).get("type")
        tt = by_id.get(r["to"], {}).get("type")
        new = rules.get((r["type"], ft, tt))
        if new and new != r["type"]:
            out.append((r, new))
    return out


def _errors(entities, relations, version):
    """Error count only — corpus checks yield warnings, so no store is needed."""
    from . import validate

    class _NoCorpus:
        def __init__(self, v):
            self.version = v

        def __contains__(self, clause):
            return False

        def haystack(self, clause):
            return ""

    errs, _ = validate.validate(entities, relations, _NoCorpus(version), version)
    return len(errs)


def main():
    ap = argparse.ArgumentParser(
        description="Retype snapshot relations after an additive ontology change.")
    ap.add_argument("--spec", default="TS 38.331")
    ap.add_argument("--version", default="19.2.0")
    ap.add_argument("--label", default=None)
    ap.add_argument("--snapshot", default=None, help="explicit path to a snapshot.json")
    ap.add_argument("--apply", action="store_true",
                    help="write the change (default: dry run). Keeps a .bak copy.")
    ap.add_argument("--samples", type=int, default=8,
                    help="edges to print per rule (default 8; 0 = all)")
    a = ap.parse_args()

    from . import snapshot
    path = a.snapshot or os.path.join(
        snapshot.dir_for(a.spec, a.version, a.label), "snapshot.json")
    if not os.path.exists(path):
        sys.exit("no snapshot at %s" % path)
    with open(path) as f:
        snap = json.load(f)
    ents, rels = snap["entities"], snap["relations"]
    version = snap.get("version") or a.version

    todo = plan(ents, rels)
    print("=" * 78)
    print("SAGE snapshot migration — %s %s" % (snap.get("spec"), version))
    print("snapshot: %s" % path)
    print("rules: %s" % ", ".join("%s(%s->%s) => %s" % (k[0], k[1], k[2], v)
                                  for k, v in RULES.items()))
    print("=" * 78)
    if not todo:
        print("\nnothing matches — snapshot already consistent with these rules.")
        return

    before = _errors(ents, rels, version)
    by_rule = {}
    for r, new in todo:
        by_rule.setdefault((r["type"], new), []).append(r)

    by_id = {e["id"]: e for e in ents}
    for (old, new), items in sorted(by_rule.items()):
        print("\n%s -> %s : %d edge(s)" % (old, new, len(items)))
        shown = items if a.samples == 0 else items[:a.samples]
        for r in shown:
            fl = by_id.get(r["from"], {}).get("label", r["from"])
            tl = by_id.get(r["to"], {}).get("label", r["to"])
            prov = (r.get("provenance") or [{}])[0]
            print("    %s --> %s" % (fl, tl))
            print("        clause %s | anchor: %r"
                  % (prov.get("clause"), (prov.get("anchor") or "")[:88]))
        if len(items) > len(shown):
            print("    … (+%d more; --samples 0 to list all)" % (len(items) - len(shown)))

    # Apply to a copy so the delta can be reported without mutating on a dry run.
    patched = [dict(r, type=RULES[(r["type"], by_id.get(r["from"], {}).get("type"),
                                   by_id.get(r["to"], {}).get("type"))])
               if (r["type"], by_id.get(r["from"], {}).get("type"),
                   by_id.get(r["to"], {}).get("type")) in RULES else r
               for r in rels]
    after = _errors(ents, patched, version)

    print("\n" + "=" * 78)
    print("validation errors: %d -> %d  (%+d)" % (before, after, after - before))
    if not a.apply:
        print("\nDRY RUN — nothing written. Review the anchors above; a rule matches on")
        print("shape alone and cannot tell 'meant the other relation' from 'stated this")
        print("one backwards'. Re-run with --apply when the sample reads correctly.")
    else:
        shutil.copy2(path, path + ".bak")
        snap["relations"] = patched
        with open(path, "w") as f:
            json.dump(snap, f, indent=2, ensure_ascii=False)
        print("\nAPPLIED — %d edge(s) retyped." % len(todo))
        print("backup: %s" % (path + ".bak"))
        print("re-check with: python3 -m pipeline.validate_debug --spec %r --version %s"
              % (snap.get("spec"), version))
    print("=" * 78)


if __name__ == "__main__":
    main()
