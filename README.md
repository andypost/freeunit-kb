# freeunit-kb

The FreeUnit knowledge base: plain markdown, rendered as a static site with
full-text search and published to GitHub Pages.

**Site:** https://andypost.github.io/freeunit-kb/

## Layout

    kb/                     the knowledge base.  Markdown is the source of truth
    report/render.py        the static site generator.  Python 3, no dependencies
    report/publish.json     which areas are published
    public/                 build output, not committed

## Build

    python3 report/render.py kb public --base=/freeunit-kb/

`--base` is the URL path the site is served from.  A project site under a user
account is served from a subpath, so this is not optional: with the wrong base
every stylesheet and internal link is broken.

The build is sliced.  `--limit=N` renders at most N pages, records progress, and
exits, so a later run resumes instead of starting over.  A single call renders
everything when it is allowed to finish.  The index page and `search.json` are
written only once every document page exists, so a partial build never publishes
a search index that disagrees with the pages.

## What is published

`report/publish.json` is an allowlist.  A directory it does not name is never
opened by the build.  The tree here is already restricted to what may be public,
so the policy is the second line of defence rather than the only one: a document
added to `kb/` by mistake still cannot reach the site.

Two controls, deliberately, because they fail differently:

1. **The tree** decides what exists.  What is not here cannot leak, and a reader
   of the source sees exactly what a reader of the site sees.
2. **The policy** decides what the build reads, and prints every exclusion with
   its reason, so the choice is auditable from the build log.

The workflow fails the deploy if `search.json` is missing, if any indexed URL has
no page, or if an excluded slug appears in the output.

## Conventions

Documents are Open Knowledge Format: an optional YAML frontmatter block whose one
required key is `type`, and an `index.md` at the root that lists every document.
Most documents here have no frontmatter and take their `type` from the directory
they live in.  Where a document states a `status`, the page shows it, and a status
other than `verified` is rendered as a lead rather than as evidence.

Every factual claim should be pinned to a commit, with anchors that name a path,
a line and a quote.  An anchor is checkable only while its commit is reachable,
so pin the merged commit and not a branch commit: a squash merge leaves a branch
commit that a later fetch will not bring back.

`index.md` should list every document, and nothing in the build enforces that.
Two flags on the renderer help you check it:

    python3 report/render.py kb public --report   # which documents would be published
    python3 report/render.py kb public --plan     # every page the build must have

Compare the second list with the entries in `index.md`. An entry naming a
document that does not exist is dropped from the rendered index, so a missing
file shows up as a shorter index rather than a broken link.

## Search

`search.json` is a prebuilt inverted index, and `assets/kb.js` reads it with no
dependency and no network beyond that one file.  It works from `file://` as well
as over HTTP.

The tokenizer keeps `.`, `-`, `_` and `/` inside a token, because this corpus is
full of `nxt_conf_validation.c`, `component-model-async` and commit ids.  A
tokenizer that splits on those characters turns a search for a source path into
a syntax error, which is what the previous SQLite FTS5 index in this knowledge
base did.  Queries are exact: an identifier that is not in the knowledge base
returns nothing rather than a page of near misses.
