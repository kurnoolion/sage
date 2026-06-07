#!/usr/bin/env python3
"""Compile the RRC pilot's four separated layers from rrc_model.py + the docx,
and validate them against each other.

Outputs:
  corpus/store/38331-19.2.0/clauses.json     (gitignored — verbatim 3GPP text)
  rrc-pilot/taxonomy/document-taxonomy.json  (clause tree structure, no text)
  rrc-pilot/taxonomy/domain-taxonomy.json    (UE/stratum/layer SKOS hierarchy)
  rrc-pilot/ontology/ontology.json           (TBox)
  rrc-pilot/knowledge-graph/kg.json          (ABox, text-free, provenance refs)

Validation: KG |= ontology (types declared; from/to obey domain/range)
            KG |= corpus   (every 38.331 provenance ref resolves to a clause)
"""
import json, os, re, sys
import docx
import rrc_model as M

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PILOT = os.path.join(ROOT, "rrc-pilot")
DOCX = os.path.join(ROOT, "corpus/extracted/38331-j20/38331-j20.docx")
CORPUS_DIR = os.path.join(ROOT, "corpus/store", "38331-%s" % M.VERSION)

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    return path

# --- 1. CORPUS: every clause's verbatim text, addressable by key -------------
# Dotted clauses (5.3.3.2) keep their number; ASN.1 "– <Name>" pseudo-headings
# (used throughout clause 6) become named units keyed "<parent>/<Name>".
def build_corpus():
    doc = docx.Document(DOCX)
    paras = doc.paragraphs
    heads = []
    for i, p in enumerate(paras):
        s = p.style.name
        if s.startswith("Heading"):
            try: lvl = int(s.split()[1])
            except: continue
            t = p.text.strip()
            num, title = (t.split("\t", 1) + [""])[:2] if "\t" in t else ("", t)
            heads.append((i, lvl, num.strip(), title.strip()))
    clauses, tree, last_dotted = {}, [], None
    for k, (i, lvl, num, title) in enumerate(heads):
        if re.match(r"^\d", num):                       # dotted clause
            key, parent, last_dotted = num, num.rsplit(".", 1)[0], num
        elif title:                                     # named ASN.1 unit
            base = last_dotted or "?"; key, parent = "%s/%s" % (base, title), base
        else:
            continue
        end = heads[k + 1][0] if k + 1 < len(heads) else len(paras)
        lines = []
        for p in paras[i + 1:end]:
            st, tx = p.style.name, p.text.rstrip()
            if not tx: continue
            if len(st) > 1 and st[0] == "B" and st[1:].isdigit():
                lines.append("   " * int(st[1:]) + tx)
            else:
                lines.append(tx)
        clauses[key] = {"id": "%s:%s:%s" % (M.SPEC, M.VERSION, key), "key": key,
                        "number": num or None, "title": title, "level": lvl,
                        "parent": parent, "text": "\n".join(lines)}
        tree.append({"key": key, "number": num or None, "title": title,
                     "level": lvl, "parent": parent})
    keys = set(clauses)                                  # null out dangling parents
    for c in list(clauses.values()) + tree:
        if c["parent"] not in keys: c["parent"] = None
    corpus = {"spec": M.SPEC, "version": M.VERSION, "release": M.RELEASE,
              "source_file": M.SOURCE_FILE, "clause_count": len(clauses),
              "clauses": clauses}
    write_json(os.path.join(CORPUS_DIR, "clauses.json"), corpus)
    return clauses, tree

# --- 2. TAXONOMY (structure only, no text) ----------------------------------
def build_taxonomy(tree):
    doc_tax = {"organisation": M.ORG, "clause_tree": tree, "clause_count": len(tree)}
    write_json(os.path.join(PILOT, "taxonomy/document-taxonomy.json"), doc_tax)
    dom_tax = {"scheme": "UE protocol-domain taxonomy (SKOS-style)",
               "concepts": M.DOMAIN_TAXONOMY}
    write_json(os.path.join(PILOT, "taxonomy/domain-taxonomy.json"), dom_tax)

# --- 3. ONTOLOGY (TBox) ------------------------------------------------------
def build_ontology():
    rels = {k: {"domain": v[0], "range": v[1], "desc": v[2], "attrs": v[3]}
            for k, v in M.RELATIONSHIP_TYPES.items()}
    onto = {"spec_scope": "%s %s" % (M.SPEC, M.VERSION),
            "entity_types": M.ENTITY_TYPES,
            "relationship_types": rels,
            "edge_metadata": {"modality": ["asn1", "prose", "curated"],
                              "confidence": ["high", "med", "low"]}}
    write_json(os.path.join(PILOT, "ontology/ontology.json"), onto)
    return onto

# --- 4. KNOWLEDGE GRAPH (ABox, text-free, provenance refs) -------------------
def parse_attrs(s):
    if not s: return {}
    if ": " in s:
        k, v = s.split(": ", 1); return {k.strip(): v.strip()}
    return {"note": s}

def build_kg():
    entities = []
    for eid, (label, typ, clause, _gloss) in M.ENTITIES.items():
        ext = clause.startswith("TS ")
        prov = {"spec": clause if ext else M.SPEC,
                "version": None if ext else M.VERSION,
                "clause": None if ext else clause,
                "external": ext}
        ent = {"id": eid, "type": typ, "label": label, "defined_in": prov}
        if eid in M.LAYER_CONCEPT:
            ent["domain_concept"] = M.LAYER_CONCEPT[eid]
        entities.append(ent)
    relations = []
    for i, (s, d, rel, mod, conf, clause, proc, attrs, quote) in enumerate(M.FACTS):
        relations.append({
            "id": "r%d" % i, "type": rel, "from": s, "to": d,
            "modality": mod, "confidence": conf, "procedure_ctx": proc,
            "attrs": parse_attrs(attrs),
            "provenance": {"spec": M.SPEC, "version": M.VERSION,
                           "clause": clause, "anchor": quote},
        })
    kg = {"spec": M.SPEC, "version": M.VERSION,
          "entity_count": len(entities), "relation_count": len(relations),
          "entities": entities, "relations": relations}
    write_json(os.path.join(PILOT, "knowledge-graph/kg.json"), kg)
    return kg

# --- 5. VALIDATION -----------------------------------------------------------
def validate(kg, onto, clauses):
    errs, warns = [], []
    etypes = set(onto["entity_types"])
    rtypes = onto["relationship_types"]
    by_id = {e["id"]: e for e in kg["entities"]}
    children = {}
    for key, c in clauses.items():
        children.setdefault(c["parent"], []).append(key)
    def haystack(cl):                     # clause title+text plus its child units
        parts = [clauses[cl]["title"], clauses[cl]["text"]]
        for ch in children.get(cl, []):
            parts += [clauses[ch]["title"], clauses[ch]["text"]]
        return "\n".join(parts)
    # entity types declared
    for e in kg["entities"]:
        if e["type"] not in etypes:
            errs.append("entity %s has undeclared type %s" % (e["id"], e["type"]))
    # entity provenance resolves into corpus (38.331 only)
    for e in kg["entities"]:
        p = e["defined_in"]
        if not p["external"] and p["clause"] not in clauses:
            warns.append("entity %s defined_in clause %s not in corpus" % (e["id"], p["clause"]))
    # relations: types, domain/range, provenance
    for r in kg["relations"]:
        if r["type"] not in rtypes:
            errs.append("relation %s has undeclared type %s" % (r["id"], r["type"])); continue
        spec = rtypes[r["type"]]
        dom, rng = spec["domain"], spec["range"]
        ft = by_id.get(r["from"], {}).get("type")
        tt = by_id.get(r["to"], {}).get("type")
        if r["from"] not in by_id: errs.append("relation %s from unknown entity %s" % (r["id"], r["from"]))
        if r["to"] not in by_id:   errs.append("relation %s to unknown entity %s" % (r["id"], r["to"]))
        if dom != ["*"] and ft and ft not in dom:
            errs.append("relation %s (%s): from-type %s not in domain %s" % (r["id"], r["type"], ft, dom))
        if rng != ["*"] and tt and tt not in rng:
            errs.append("relation %s (%s): to-type %s not in range %s" % (r["id"], r["type"], tt, rng))
        cl = r["provenance"]["clause"]
        if cl not in clauses:
            warns.append("relation %s provenance clause %s not in corpus" % (r["id"], cl))
        else:                                   # anchor should locate in clause (incl child units)
            hay = haystack(cl)
            anc = (r["provenance"]["anchor"] or "").strip(" .;:,")
            if anc and anc not in hay:
                w = anc.split(" ")
                if not any(" ".join(w[st:]) in hay for st in range(1, max(1, len(w) - 2))):
                    warns.append("relation %s anchor not found in %s: %r" % (r["id"], cl, anc[:40]))
    return errs, warns

def main():
    clauses, tree = build_corpus()
    build_taxonomy(tree)
    onto = build_ontology()
    kg = build_kg()
    errs, warns = validate(kg, onto, clauses)
    print("=== RRC pilot layers built ===")
    print("corpus  : %d clauses (38.331 %s)" % (len(clauses), M.VERSION))
    print("taxonomy: document spine (%d clauses) + domain (%d concepts)" % (len(tree), len(M.DOMAIN_TAXONOMY)))
    print("ontology: %d entity types, %d relationship types" % (len(onto["entity_types"]), len(onto["relationship_types"])))
    print("kg      : %d entities, %d relations" % (kg["entity_count"], kg["relation_count"]))
    print("\n=== validation ===")
    print("errors  :", len(errs))
    for e in errs: print("  ERR ", e)
    print("warnings:", len(warns))
    for w in warns: print("  warn", w)
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
