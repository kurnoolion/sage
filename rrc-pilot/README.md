# RRC pilot — layered baseline

The **baseline** structure for the project, built and validated for the RRC
connection-establishment + reconfiguration slice of **TS 38.331 v19.2.0**.

## The model: three layers (+ a concept-scheme adjunct)

A taxonomy is *not* a separate peer of the ontology — an ontology already contains a
taxonomy (its type hierarchy). So the clean model is **three layers**:

| Layer | Job | Artifact | Committed? |
|---|---|---|---|
| **Ontology** (TBox) | Entity **type hierarchy** (`subtype_of`) + relationship types (`domain→range`) + attributes | `ontology/ontology.json` | Yes |
| **Knowledge graph** (ABox) | Instances + typed relationships, **text-free**, with provenance refs into the corpus | `knowledge-graph/kg.json` | Yes |
| **Corpus document store** | Complete **verbatim** clause text (prose + ASN.1), addressable | `corpus/store/38331-19.2.0/clauses.json` | No — 3GPP copyright |

Two **adjuncts** that hang off these (not peer layers):

- **Domain concept scheme** (`concept-scheme/domain-concept-scheme.json`) — the curated
  protocol-stack skeleton `UE → AS/NAS → RRC/MAC/…/IMS` (SKOS-style). Each concept is a
  KG instance of its ontology type (`RRC` is a `ProtocolLayer`, `AS` a `Stratum`). It is
  the **hub**: every domain entity links to it via `IN_LAYER`; concepts nest via `BROADER`.
  It's the stable cross-release / cross-SDO join point. *Why separate file:* SKOS interop
  + it's hand-curated and changes on a different cadence than extracted facts.
- **Corpus index / document taxonomy** (`corpus-index/document-index.json`) — the
  org chain + full clause tree (titles, no body text). This is the **corpus's table of
  contents**, not part of the ontology.

Why ontology/KG are kept *separate* from the corpus: the structured layers are selective
(you reason/traverse over them); the corpus is complete/verbatim (you retrieve exact
normative text). The KG **links into** the corpus via `DEFINED_IN` / provenance — it never
embeds bulk text. 100% coverage lives in the corpus; the KG aims for conceptual coverage
vs. competency questions. See `docs/research/04-*`.

## Files

- `rrc_model.py` — **single source of truth**: instances (FACTS), ontology (entity-type
  hierarchy + relationship types), and the domain concept scheme (CONCEPTS).
- `build_layers.py` — compiles `rrc_model.py` + the docx into all layers, then validates:
  - **KG ⊨ ontology**: every type declared; every relation's `from`/`to` obey `domain`/`range`.
  - **KG ⊨ corpus**: every (non-curated) provenance clause resolves; every anchor locates in
    that clause's text (incl. named ASN.1 sub-units like `6.2.2/RRCSetupRequest`).

## Rebuild

```bash
python3 rrc-pilot/build_layers.py        # writes corpus + ontology + concept-scheme + corpus-index + kg, validates
python3 corpus/viz/build_rrc_graph.py    # renders the viz by CONSUMING kg.json + corpus store
```

## How the concept scheme is used

- **Faceted navigation / scoping** — "all RRC procedures", per-layer ingestion.
- **Cross-spec / cross-SDO anchoring** — the shared hub when NAS/IMS/other SDOs are added.
- **Roll-up reasoning** — stratum-level questions; per-layer metrics.
- **Extraction grounding** — layer context constrains/validates LLM-extracted triples.

In the visualization, toggle **Concept scheme** to show the concepts (diamonds) and the
`IN_LAYER` / `BROADER` edges.

## Notes

- **Store-agnostic** plain JSON; doesn't prejudge the RDF/SKOS-vs-property-graph decision.
- **3GPP doc-structure finding:** clause 6 keys ASN.1 message/IE defs under named
  `– <Name>` pseudo-headings, captured as corpus keys like `6.2.2/RRCSetupRequest`.
- The visualization is a **view** over the layers, not a source of truth.
