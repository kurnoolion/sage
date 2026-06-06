# Structure conventions

Defines what counts as a "module" in this repository and how language-native visibility maps
to `pub` / `internal` for the `regen-map` skill.

> **PROVISIONAL.** The tech stack was deliberately left undecided at project-init (the user chose
> not to jump to implementation). Python is assumed below as the likely default (ASN.1 parsing +
> local-LLM tooling), but it is **unconfirmed**. Confirm or replace this file's language and
> conventions during the architecture phase, **before the first `regen-map` run** — and re-check
> after the store decision (an RDF/SPARQL stack vs. a property-graph stack may shift the layout).

## Module definition

Each top-level directory under `src/` is a module. A module's `MODULE.md` lives at
`src/<module>/MODULE.md`. A directory is a module when it contains an `__init__.py` and exposes a
public surface other modules import.

## Visibility mapping

- Top-level name **not** prefixed with `_` (functions, classes, constants) → pub
- Top-level name prefixed with `_` → internal
- Name listed in the module's `__all__` → pub (authoritative when `__all__` is present)
- Anything under a `_`-prefixed subpackage / `_internal/` → internal

## Description source

Used by `regen-map` to generate per-file one-liners in the **Project File Structure** section of
`MAP.md`:

- `*.py`: first line of the module docstring. If absent, no description.
- `*.sh`: first line of the top comment block after the shebang. If absent, no description.
- Directories with `MODULE.md`: first sentence of the Purpose section.
- Other files / directories: no automatic description (path-only row).

Rows are alphabetical within each directory; files and directories intermix alphabetically.

## Module doc schema

Each module has `src/<module>/MODULE.md` with the following curated sections (plus a regen-only
Structure section):

- **Owner** *(optional)* — single contributor owning the module; omit if shared or unassigned.
- **Purpose** — 1-2 sentences.
- **Public surface** — signatures + semantics. Includes trait / interface implementations callers rely on.
- **Invariants** — what callers can count on (threading, state, ordering).
- **Key choices** — each linked to DECISIONS.md by `[D-XXX]`.
- **Non-goals** — deliberate omissions.
- **Structure** — regen-only; bounded by `<!-- BEGIN:STRUCTURE -->` / `<!-- END:STRUCTURE -->`; never hand-edited.
- **Depends on** / **Depended on by** — links to other MODULE.md.
- **Deferred** *(optional)* — planned-but-unbuilt behaviors; read by `drift-check` to classify
  matching items as `[DEFERRED]` instead of drift.
