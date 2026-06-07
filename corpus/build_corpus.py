#!/usr/bin/env python3
"""Spec-agnostic corpus builder.

Walks a 3GPP spec .docx in document order — capturing both paragraphs AND tables
(3GPP specs put a lot of normative content in tables that python-docx's
`.paragraphs` skips) — and emits, for the whole spec:

  corpus/store/<key>/clauses.json        verbatim, clause-addressable (gitignored)
  corpus/store/<key>/document-index.json the document hierarchy (structure only)

Dotted/lettered clauses (5.1.1, A.4, 3A) keep their number; named pseudo-headings
(e.g. ASN.1 "– <Name>") become keys "<parent>/<Name>".

Usage: build_corpus.py <docx> "<SPEC>" <VERSION> <RELEASE>
"""
import json, os, re, sys
import docx
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def iter_blocks(doc):
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):   yield ("p", Paragraph(child, doc))
        elif isinstance(child, CT_Tbl): yield ("t", Table(child, doc))

def head_level(style):
    if style.startswith("Heading"):
        try: return int(style.split()[1])
        except: return None
    m = re.match(r"^H(\d)$", style)
    return int(m.group(1)) if m else None

def table_text(t):
    rows = []
    for r in t.rows:
        rows.append(" | ".join(c.text.strip().replace("\n", " ") for c in r.cells))
    return "\n".join(rows)

def build(docx_path, spec, version, release):
    doc = docx.Document(docx_path)
    key = spec.replace("TS ", "").replace(".", "") + "-" + version
    clauses, order, last_keyed = {}, [], None
    cur = None  # current clause key
    tbl_count = 0
    def ensure(k, num, title, lvl, parent):
        if k not in clauses:
            clauses[k] = {"id": "%s:%s:%s" % (spec, version, k), "key": k,
                          "number": num or None, "title": title, "level": lvl,
                          "parent": parent, "text": "", "tables": 0}
            order.append(k)
    for kind, blk in iter_blocks(doc):
        if kind == "p":
            lvl = head_level(blk.style.name)
            if lvl is not None and blk.text.strip():
                t = blk.text.strip()
                num, title = (t.split("\t", 1) + [""])[:2] if "\t" in t else ("", t)
                num = num.strip()
                if num and num[0].isalnum():
                    k, parent, last_keyed = num, (num.rsplit(".", 1)[0] if "." in num else None), num
                else:
                    base = last_keyed or "_"; k, parent = "%s/%s" % (base, title.strip()), base
                ensure(k, num, title.strip(), lvl, parent)
                cur = k
            else:
                if cur is None:
                    ensure("_preamble", "", "(preamble)", 0, None); cur = "_preamble"
                tx = blk.text.rstrip()
                if tx:
                    st = blk.style.name
                    ind = "   " * int(st[1:]) if (len(st) > 1 and st[0] == "B" and st[1:].isdigit()) else ""
                    clauses[cur]["text"] += ("\n" if clauses[cur]["text"] else "") + ind + tx
        else:  # table
            if cur is None:
                ensure("_preamble", "", "(preamble)", 0, None); cur = "_preamble"
            txt = table_text(blk)
            if txt.strip():
                clauses[cur]["text"] += ("\n\n[TABLE]\n" if clauses[cur]["text"] else "[TABLE]\n") + txt
                clauses[cur]["tables"] += 1; tbl_count += 1
    keys = set(clauses)
    for c in clauses.values():
        if c["parent"] not in keys: c["parent"] = None

    out_dir = os.path.join(ROOT, "corpus/store", key)
    os.makedirs(out_dir, exist_ok=True)
    corpus = {"spec": spec, "version": version, "release": release,
              "source_file": os.path.basename(docx_path), "clause_count": len(clauses),
              "table_count": tbl_count, "clauses": clauses}
    json.dump(corpus, open(os.path.join(out_dir, "clauses.json"), "w"), ensure_ascii=False)
    index = {"spec": spec, "version": version, "release": release,
             "clause_count": len(clauses),
             "clause_tree": [{"key": k, "number": clauses[k]["number"],
                              "title": clauses[k]["title"], "level": clauses[k]["level"],
                              "parent": clauses[k]["parent"]} for k in order]}
    json.dump(index, open(os.path.join(out_dir, "document-index.json"), "w"), ensure_ascii=False, indent=1)

    total = sum(len(c["text"]) for c in clauses.values())
    print("corpus: %s %s" % (spec, version))
    print("  clauses : %d" % len(clauses))
    print("  tables  : %d captured" % tbl_count)
    print("  text    : %.1f MB verbatim" % (total / 1e6))
    print("  -> %s/{clauses.json,document-index.json}" % out_dir)
    return corpus

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__); sys.exit(2)
    build(*sys.argv[1:])
