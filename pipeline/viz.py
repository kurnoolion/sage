"""Render a pipeline snapshot into the generic KG viewer.

    python3 -m pipeline.viz [--spec "TS 24.229"] [--version 19.6.0]

Exports the shared ontology (pipeline/ontology.py) to a JSON the viewer can read
(its entity-type list drives node colours + the legend, so IMS SIP types render
properly), then invokes the generic viewer (rrc-pilot/viz/build_kg_view.py)
pointed at the snapshot. Both outputs land in the snapshot dir (gitignored).
"""
import argparse
import json
import os
import subprocess
import sys

from . import config, ontology, snapshot

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VIEWER = os.path.join(ROOT, "rrc-pilot", "viz", "build_kg_view.py")


def export_ontology(path):
    """Dump the shared TBox in the viewer-compatible JSON shape."""
    obj = {
        "entity_types": {n: {"desc": s["desc"], "subtype_of": s["subtype_of"], "attrs": s["attrs"]}
                         for n, s in ontology.ENTITY_TYPES.items()},
        "relationship_types": {n: {"domain": s["domain"], "range": s["range"],
                                   "desc": s["desc"], "attrs": s["attrs"]}
                               for n, s in ontology.RELATIONSHIP_TYPES.items()},
    }
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def render(spec, version, label=None):
    config.get(spec, version)                      # validate spec is known
    snap_dir = snapshot.dir_for(spec, version, label)
    snap = os.path.join(snap_dir, "snapshot.json")
    if not os.path.exists(snap):
        sys.exit("no snapshot at %s\n  run: python3 -m pipeline.run --spec %r --version %s%s"
                 % (snap, spec, version, " --label %s" % label if label else ""))
    onto = os.path.join(snap_dir, "ontology.json")
    out = os.path.join(snap_dir, "kg-view.html")
    export_ontology(onto)
    title = "%s %s%s — SAGE extraction snapshot" % (spec, version, " [%s]" % label if label else "")
    subprocess.run([sys.executable, VIEWER, "--kg", snap, "--ontology", onto, "--out", out,
                    "--title", title], check=True)
    print("open via file://%s" % out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default="TS 24.229")
    ap.add_argument("--version", default="19.6.0")
    ap.add_argument("--label", default=None, help="render the snapshot for this run label")
    a = ap.parse_args()
    render(a.spec, a.version, a.label)


if __name__ == "__main__":
    main()
