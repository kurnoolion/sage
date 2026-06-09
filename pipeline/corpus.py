"""Load a frozen corpus store (produced by corpus/build_corpus.py).

Store layout:  <store_dir>/clauses.json
    { spec, version, release, clause_count, table_count,
      clauses: { <key>: {id, key, number, parent, level, title, text, tables} } }

``key`` is the clause number, except for named ASN.1 / SIP sub-units which are
keyed ``<number>/<Name>`` (e.g. "6.2.2/RRCSetupRequest"). Provenance anchors are
validated against a clause's title+text *plus its children's* (see validate.py).
"""
import json
import os


class Corpus:
    def __init__(self, store_dir):
        self.store_dir = store_dir
        with open(os.path.join(store_dir, "clauses.json")) as f:
            doc = json.load(f)
        self.spec = doc["spec"]
        self.version = doc["version"]
        self.release = doc.get("release")
        self.clauses = doc["clauses"]
        # parent -> [child keys]
        self.children = {}
        for k, c in self.clauses.items():
            self.children.setdefault(c.get("parent"), []).append(k)

    def __contains__(self, key):
        return key in self.clauses

    def __getitem__(self, key):
        return self.clauses[key]

    def get(self, key, default=None):
        return self.clauses.get(key, default)

    def haystack(self, key):
        """A clause's searchable text: its own title+text plus its children's."""
        c = self.clauses[key]
        parts = [c.get("title", ""), c.get("text", "")]
        for ch in self.children.get(key, []):
            cc = self.clauses[ch]
            parts += [cc.get("title", ""), cc.get("text", "")]
        return "\n".join(parts)

    def items(self):
        return self.clauses.items()
