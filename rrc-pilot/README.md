# RRC pilot — layered baseline

The **baseline** structure for the project, built and validated for the RRC
connection-establishment + reconfiguration slice of **TS 38.331 v19.2.0**.

## The model: three layers

A taxonomy is *not* a separate peer of the ontology — an ontology already contains a
taxonomy (its type hierarchy). So the clean model is **three layers**, each answering a
different question:

| | **Ontology** | **Knowledge graph** | **Corpus** |
|---|---|---|---|
| Role | the **schema** | the **data** | the **source** |
| Holds | entity *types*, relationship *types* (`domain→range`), the `subtype_of` hierarchy, attributes | *instances* + typed relationships, **text-free**, each with a provenance ref | complete **verbatim** clause text (prose + ASN.1), addressable |
| Answers | "What **can** exist & relate?" | "What **does** exist & relate, and where?" | "What does the spec **actually say**?" |
| Churn | small, stable | grows with every fact | fixed per spec version |
| Artifact | `ontology/ontology.json` | `knowledge-graph/kg.json` | `corpus/store/38331-19.2.0/clauses.json` |
| Committed? | yes | yes | no — 3GPP copyright |

### One fact across all three layers

Take the fact *"RRC connection establishment starts timer T300."*

- **Ontology** — stores only the *types and the rule* that make this expressible; it never
  names `T300`:
  ```
  entity types:        Procedure (subtype_of Entity), Timer (subtype_of Entity)
  relationship type:   STARTS  domain=[Procedure]  range=[Timer]
  ```
- **Knowledge graph** — stores the *specific fact*, text-free, with a pointer into the corpus;
  it never stores the prose:
  ```
  entity   P_setup : Procedure  "RRC connection establishment"
  entity   T_t300  : Timer      "T300"
  relation P_setup --STARTS--> T_t300
           modality=prose  confidence=high
           provenance: clause 5.3.3.2, anchor "start timer T300"
  ```
- **Corpus** — stores the *exact words*; it never says `STARTS` or `Procedure`:
  ```
  clause 5.3.3.2 "Initiation":
    "... 1> start timer T300;
         1> initiate transmission of the RRCSetupRequest message ..."   (the whole clause)
  ```

**What each layer deliberately does NOT hold:** the ontology has no `T300`; the KG has no
prose (only a short locator anchor); the corpus has no notion of `STARTS`/`Procedure`.

### How the layers connect

- **KG → Ontology** (instance-of): every entity's `type` and every relation's `type` must be
  declared in the ontology, and a relation's `from`/`to` must satisfy its `domain`/`range`.
  Enforced by `build_layers.py` as **KG ⊨ ontology**.
- **KG → Corpus** (provenance): every relation/entity carries `(clause, anchor)` that resolves
  into the corpus. Enforced as **KG ⊨ corpus**.

So `P_setup —STARTS→ T_t300` is valid *only* because the ontology declares `STARTS:
Procedure→Timer`, and it's *traceable* only because its anchor `"start timer T300"` resolves
in corpus clause `5.3.3.2`.

### Which layer answers which question

| Question | Layer |
|---|---|
| "Can a procedure start a timer?" | Ontology |
| "Which timer does RRC setup start, and where is that defined?" | Knowledge graph |
| "What exactly does the spec say at that point?" | Corpus |

### Two adjuncts (not peer layers)

- **Domain concept scheme** (`concept-scheme/domain-concept-scheme.json`) — curated
  protocol-stack skeleton `UE → AS/NAS → RRC/MAC/…/IMS` (SKOS-style). Each concept is a KG
  instance of its ontology type and the cross-spec/SDO **hub**. *Example:* `RRC` is a
  `ProtocolLayer`; `RRC —BROADER→ AS —BROADER→ UE`; `P_setup —IN_LAYER→ RRC`.
- **Corpus index** (`corpus-index/document-index.json`) — the corpus's table of contents:
  org chain + clause tree (titles only, no body). *Example:* `3GPP/RAN2 → series 38 → 38.331
  → 5 → 5.3 → 5.3.3 → 5.3.3.2 "Initiation"`.

**Why ontology/KG are kept separate from the corpus:** the structured layers are *selective*
(you reason/traverse over them); the corpus is *complete/verbatim* (you retrieve exact
normative text). 100% **text** coverage lives in the corpus; the ontology/KG aim for
**conceptual** coverage vs. competency questions, not text coverage. See `docs/research/04-*`.

## Files

- `rrc_model.py` — **single source of truth**: instances (FACTS), ontology (entity-type
  hierarchy + relationship types), and the domain concept scheme (CONCEPTS).
- `build_layers.py` — compiles `rrc_model.py` + the docx into all layers, then validates:
  - **KG ⊨ ontology**: every type declared; every relation's `from`/`to` obey `domain`/`range`.
  - **KG ⊨ corpus**: every (non-curated) provenance clause resolves; every anchor locates in
    that clause's text (incl. named ASN.1 sub-units like `6.2.2/RRCSetupRequest`).

## Rebuild

```bash
python3 rrc-pilot/build_layers.py        # builds + validates all layers, then regenerates the KG view
# (add --no-view to skip the viewer)
```

## Viewing the KG (incremental)

`build_layers.py` regenerates `rrc-pilot/viz/kg-view.html` — a **generic, data-driven,
self-contained** viewer (the script `viz/build_kg_view.py` is reusable for any `kg.json`;
the HTML is gitignored because it embeds spec prose). Open it via `file://` — no server.

Workflow: **rebuild → refresh the browser tab.** The viewer:
- colours nodes from the ontology's entity types and auto-builds **focus buttons** from the
  data's `procedure_ctx` values;
- toggles for **Corpus clauses** (Hierarchy A) and **Concept scheme** (`IN_LAYER`/`BROADER`);
- **highlights what's new since you last opened it** (green rings, via `localStorage`), with
  a **Mark all as seen** reset and a stats panel (counts by type + "N new") — so as the KG
  grows clause-by-clause you immediately see exactly what was added.

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
- The visualization is a **view** over the layers, not a source of truth. At full
  multi-spec scale (10⁴–10⁵ nodes) the eventual viewer is the chosen store's browser
  (Neo4j/Memgraph); this self-contained viewer carries the pilots.
