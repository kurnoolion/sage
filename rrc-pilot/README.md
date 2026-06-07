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

### Three hierarchies — don't confuse them

There are **three** hierarchies. Only the **type hierarchy** lives in the ontology; the
other two are their own files.

| Hierarchy | Organizes | File | Tree edge |
|---|---|---|---|
| **Type hierarchy** | kinds of entities | `ontology/ontology.json` | `subtype_of` |
| **Domain hierarchy** (concept scheme) | the protocol stack | `concept-scheme/domain-concept-scheme.json` | `broader` |
| **Document hierarchy** (corpus index) | the spec's structure | `corpus-index/document-index.json` | `parent` |

The **type hierarchy** was *folded into* the ontology: each entity type carries a
`subtype_of` (root `Entity`), so there is no separate "type taxonomy" file — read
`ontology.json` to see it. The other two were **not** folded in.

#### Domain hierarchy (concept scheme)

The curated protocol stack `UE → AS/NAS → RRC/MAC/…/IMS`, SKOS-style. Each concept is a KG
**instance** whose `type` is an *ontology* entity type, and whose `broader` is its parent in
the tree. KG entities attach via `IN_LAYER`. It's the cross-spec/SDO **hub**.

*Example 1 — RRC (in v1 scope, populated):*
```
concept  C_RRC   type=ProtocolLayer   broader=C_AS        # C_RRC → C_AS → C_UE
fact     P_setup (RRC connection establishment) --IN_LAYER--> C_RRC
         (41 RRC entities currently classified here)
```
*Example 2 — IMS (out of v1 scope, empty until the IMS pilot):*
```
concept  C_IMS   type=ProtocolLayer   broader=C_NAS       # C_IMS → C_NAS → C_UE
         (0 entities now; fills when TS 24.229 is modelled)
```
So `type` → ontology, `broader` → the domain tree, `IN_LAYER` → the KG. View it as a graph:
`rrc-pilot/viz/concept-view.html` (top-down tree, each box showing its `IN_LAYER` count).

#### Document hierarchy (corpus index)

The corpus's table of contents: the org chain + clause tree (titles only, no body text).
Each clause node carries a `parent`. It pairs with the **corpus** (same clause keys), and KG
provenance / `DEFINED_IN` point at clauses indexed here.

*Example:*
```
org        3GPP → TSG RAN → RAN2 → series 38 → TS 38.331 (Rel-19, v19.2.0)
clause     5.3.3.2 "Initiation"   parent=5.3.3   (→ 5.3 → 5 → spec root)
```
Browse it visually via the **Corpus clauses** toggle in `kg-view.html`.

**Why ontology/KG are kept separate from the corpus:** the structured layers are *selective*
(you reason/traverse over them); the corpus is *complete/verbatim* (you retrieve exact
normative text). 100% **text** coverage lives in the corpus; the ontology/KG aim for
**conceptual** coverage vs. competency questions, not text coverage. See `docs/research/04-*`.

## Multiple releases (D-011)

Releases are modelled by **shared entity identity + versioned assertions**, not separate graphs:

- **Identity is release-agnostic** — a node's id is semantic (`type+name+layer`), never the
  clause number (clauses renumber across releases). `T300` is one node across all releases.
- **`Release` is a first-class entity**, ordered via `NEXT_RELEASE` (`Rel-15 → … → Rel-19`).
- **Every entity & relation is release-stamped**: `observed_in` (releases ingested from),
  `introduced_in`, `valid_until` (null = current), `supersedes`. Unchanged facts are stored
  once with an open range — size is O(distinct facts), not O(facts × releases).
- **Time-varying attributes are sets of immutable value-assertions** (SCD-2). All prior values
  are kept; e.g. T300:
  ```
  A1 value=v1 valid Rel-15..Rel-16   A2 value=v2 valid Rel-17..Rel-18 (supersedes A1)
  A3 value=v3 valid Rel-19..(open)   (supersedes A2)
  ```
  "value at Rel-17" = the assertion covering Rel-17 (A2); "current" = the open one (A3); each
  points at its own release's corpus clause.
- **Lifecycle is computed, not extracted** — extract each release as an independent snapshot;
  a deterministic diff opens/closes assertions and builds the `supersedes` chain.

- **Provenance is a per-version list** — `[{release, spec, version, clause, anchor}, …]`, one
  entry per release the fact was observed in. The **clause number is recorded per version**, so
  renumbering across releases is captured, never assumed stable; identity (the `(s,p,o)` over
  semantic ids) is independent of the clause number. Each entry's anchor is validated against
  *its own* version's corpus store. A renumber-only change just adds a provenance entry (merge);
  a content change is a supersede (new assertion). Removed/Void → `valid_until` set.

Corpus stays per-version (one frozen version per release). Currently only Rel-19 is ingested, so
everything is `observed_in: [Rel-19]`, single-entry provenance, `introduced_in: null` until
earlier releases backfill it.

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

`build_layers.py` regenerates two self-contained viewers (HTML gitignored — embeds spec
prose; the generator scripts under `viz/` are committed and reusable):
- **`viz/kg-view.html`** — the knowledge graph (entities + relationships + corpus).
- **`viz/concept-view.html`** — the **domain hierarchy** as a top-down tree (concepts +
  `BROADER`), each concept showing its `IN_LAYER` entity count and v1-scope status.

Open either via `file://` — no server.

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
