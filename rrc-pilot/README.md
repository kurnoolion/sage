# RRC pilot — four-layer baseline

This is the **baseline** structure for the project: a clean separation of the four layers,
built and validated for the RRC connection-establishment + reconfiguration slice of
**TS 38.331 v19.2.0**. Everything else in the project follows this shape.

## The four layers

| Layer | Job | Artifact | Committed? |
|---|---|---|---|
| **Corpus document store** | Complete **verbatim** clause text (prose + ASN.1), addressable by clause key | `corpus/store/38331-19.2.0/clauses.json` | No — 3GPP copyright (gitignored) |
| **Taxonomy** | *Structure only* — document spine (org + full clause tree, titles, no body text) and the UE domain hierarchy | `taxonomy/document-taxonomy.json`, `taxonomy/domain-taxonomy.json` | Yes |
| **Ontology** (TBox) | Entity types + relationship types with `domain → range` + attributes | `ontology/ontology.json` | Yes |
| **Knowledge graph** (ABox) | Instances + typed relationships, **text-free**, each with a provenance ref into the corpus | `knowledge-graph/kg.json` | Yes |

Why this split: the ontology/taxonomy/KG are the *structured, selective* layers (you reason
and traverse over them); the corpus is the *complete, verbatim* layer (you retrieve exact
normative text from it). The KG **links into** the corpus via `DEFINED_IN` / provenance refs —
it never embeds bulk text. 100%-coverage lives in the corpus; the KG aims for conceptual
coverage against competency questions, not text coverage. See `docs/research/04-*`.

## Files

- `rrc_model.py` — **single source of truth**: entity/relationship instances (FACTS),
  the ontology (TBox), and the domain taxonomy. Hand-curated from the spec.
- `build_layers.py` — compiles `rrc_model.py` + the docx into the four layers, then
  **validates** them:
  - KG ⊨ ontology: every entity/relationship type is declared; every relation's
    `from`/`to` obey the declared `domain`/`range`.
  - KG ⊨ corpus: every provenance clause resolves, and every anchor locates in that
    clause's text (incl. its named ASN.1 sub-units).

## Rebuild

```bash
python3 rrc-pilot/build_layers.py        # writes corpus store + taxonomy + ontology + kg, validates
python3 corpus/viz/build_rrc_graph.py    # renders the viz by CONSUMING kg.json + corpus store
```

## Notes

- **Store-agnostic on purpose.** Plain JSON; does not prejudge the deferred
  RDF/SKOS-vs-property-graph decision. Loads into either later.
- **3GPP doc-structure finding.** Clause 6 (ASN.1) organises message/IE definitions under
  named `– <Name>` pseudo-headings, not dotted numbers. The corpus captures these as keys
  like `6.2.2/RRCSetupRequest`, so message provenance points at the exact ASN.1 unit.
- The visualization is a **view** over the layers, not a source of truth.
