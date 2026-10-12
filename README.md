# freeunit-kb

The FreeUnit knowledge base: plain markdown, rendered as a static site with
full-text search and published to GitHub Pages.

**Site:** https://andypost.github.io/freeunit-kb/

## Layout

    kb/                     the knowledge base.  Markdown is the source of truth
    report/render.py        the static site generator.  Python 3, no dependencies
    report/publish.json     which areas are published, and what is excluded
    public/                 build output, not committed

## Build

    python3 report/render.py kb public --base=/freeunit-kb/

The `--base` argument is the URL path the site is served from.  A project site
under a user account is served from a subpath, so this is not optional: with the
wrong base every stylesheet and link is broken.

## How publishing is decided

`report/publish.json` is an allowlist.  A directory that the policy does not
name is never opened by the build, so `strategy/` and `team.md` are absent from
this repository as well as from the site.  A second rule drops documents whose
subject is a different project, by counting mentions in the text rather than by
path, because those documents live beside FreeUnit ones in the same directory.

Two independent controls, deliberately:

1. **The source tree** carries only what may be public.  What is not here cannot
   leak.
2. **The policy** decides what the build reads, and prints every exclusion with
   its reason, so the choice can be audited from the build log.

## Conventions

Markdown documents are Open Knowledge Format: an optional YAML frontmatter block
whose one required key is `type`, and an `index.md` at the root that lists every
document.  Documents without frontmatter are normal here and get their `type`
from the directory they live in.  Where a document says `status`, the page shows
it: a status that is not `verified` is rendered as a lead rather than as
evidence.

Every fact should be pinned to a commit, with anchors that name a path, a line
and a quote.  An anchor is checkable only while that commit is reachable, so pin
the merged commit rather than a branch commit: a squash merge leaves a branch
commit that a later fetch will not bring back.
