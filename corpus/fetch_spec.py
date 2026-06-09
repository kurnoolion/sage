#!/usr/bin/env python3
"""Fetch a 3GPP spec and (re)build its corpus store — Option B, rebuild on-prem.

The corpus is gitignored (3GPP copyright), so it never travels with ``git pull``.
This script rebuilds it on any machine: it reuses NORA's downloader
(``~/work/nora/core/src/standards``) to pull the spec DOCX from the public
GSMA/3GPP HuggingFace dataset (stdlib urllib — no auth, no ``requests``),
converts a legacy ``.doc`` to ``.docx`` via LibreOffice when that is the only
form served, then runs ``build_corpus.py`` to emit
``corpus/store/<compact>-<version>/{clauses.json,document-index.json}``.

The version is pinned exactly (e.g. 19.6.0 → 3GPP code ``j60``) so the rebuilt
store matches what ``pipeline/config.py`` and the committed snapshots expect —
unlike NORA's downloader, which always takes a release's latest minor.

Usage:
    python3 corpus/fetch_spec.py "TS 24.229" 19.6.0 Rel-19
    python3 corpus/fetch_spec.py "TS 38.331" 19.2.0 Rel-19
    python3 corpus/fetch_spec.py --all            # every spec SAGE uses

NORA must be checked out (default ~/work/nora; override with --nora-root or the
SAGE_NORA_ROOT env var). LibreOffice is required only for specs served as .doc
(e.g. TS 24.229 Rel-19).
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(ROOT, "corpus", "raw")
BUILDER = os.path.join(ROOT, "corpus", "build_corpus.py")

# (spec, version, release) — the specs SAGE's pipeline is configured for.
SPECS = [
    ("TS 24.229", "19.6.0", "Rel-19"),
    ("TS 38.331", "19.2.0", "Rel-19"),
]


def _nora_root(explicit=None):
    root = explicit or os.environ.get("SAGE_NORA_ROOT") or os.path.expanduser("~/work/nora")
    if not os.path.isdir(os.path.join(root, "core", "src", "standards")):
        sys.exit("NORA standards module not found under %s\n"
                 "  pass --nora-root <path> or set SAGE_NORA_ROOT" % root)
    return root


def fetch_docx(spec, version, release, nora_root):
    """Download the exact spec version as a .docx (converting .doc if needed).

    Returns the local path to the .docx under corpus/raw/.
    """
    if nora_root not in sys.path:
        sys.path.insert(0, nora_root)
    from core.src.standards.hf_source import HuggingFaceSource
    from core.src.standards.spec_downloader import SpecDownloader
    from core.src.standards.spec_resolver import (
        spec_to_compact, spec_to_series, version_to_code)

    compact = spec_to_compact(spec.replace("TS ", "").strip())   # "24.229" -> "24229"
    series = spec_to_series(spec.replace("TS ", "").strip())     # -> "24"
    code = version_to_code(version)                              # "19.6.0" -> "j60"
    if not code:
        sys.exit("could not encode version %r for %s" % (version, spec))
    release_num = int(version.split(".")[0])

    hf = HuggingFaceSource()
    dir_path = "original/Rel-%d/%s_series" % (release_num, series)
    files = hf._list_directory(dir_path)
    if not files:
        sys.exit("HF: nothing listed at %s (network/proxy?)" % dir_path)

    # Exact-version match, preferring .docx over .doc.
    stem = ("%s-%s" % (compact, code)).lower()
    match = next((f for f in files if f.lower() == stem + ".docx"), None) \
        or next((f for f in files if f.lower() == stem + ".doc"), None)
    if not match:
        avail = sorted(f for f in files if f.lower().startswith(compact.lower() + "-"))
        sys.exit("HF: %s %s (%s) not found at %s\n  available: %s"
                 % (spec, version, code, dir_path, avail or "(none)"))

    os.makedirs(RAW_DIR, exist_ok=True)
    dest = os.path.join(RAW_DIR, match)
    if os.path.exists(dest):
        print("  cached: %s" % match)
    else:
        url = "%s/resolve/main/%s/%s" % (hf._dataset_base, dir_path, match)
        print("  downloading %s ..." % match)
        if not hf._download_file(url, __import__("pathlib").Path(dest)):
            sys.exit("HF: download failed for %s" % url)

    if dest.lower().endswith(".doc"):
        print("  converting .doc -> .docx (LibreOffice) ...")
        converted = SpecDownloader._convert_doc_to_docx(__import__("pathlib").Path(dest))
        if not converted:
            sys.exit("LibreOffice .doc->.docx conversion failed (is libreoffice installed?)")
        dest = str(converted)
    return dest


def build_store(docx_path, spec, version, release):
    subprocess.run([sys.executable, BUILDER, docx_path, spec, version, release], check=True)


def run_one(spec, version, release, nora_root):
    print("== %s %s (%s) ==" % (spec, version, release))
    docx = fetch_docx(spec, version, release, nora_root)
    build_store(docx, spec, version, release)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help='e.g. "TS 24.229"')
    ap.add_argument("version", nargs="?", help="e.g. 19.6.0")
    ap.add_argument("release", nargs="?", help="e.g. Rel-19")
    ap.add_argument("--all", action="store_true", help="rebuild every spec SAGE uses")
    ap.add_argument("--nora-root", default=None,
                    help="path to the NORA checkout (default ~/work/nora or SAGE_NORA_ROOT)")
    a = ap.parse_args()
    nora_root = _nora_root(a.nora_root)

    if a.all:
        for spec, version, release in SPECS:
            run_one(spec, version, release, nora_root)
    elif a.spec and a.version:
        release = a.release or ("Rel-%d" % int(a.version.split(".")[0]))
        run_one(a.spec, a.version, release, nora_root)
    else:
        ap.error("give SPEC VERSION [RELEASE], or --all")


if __name__ == "__main__":
    main()
