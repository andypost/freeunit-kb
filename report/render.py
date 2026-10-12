#!/usr/bin/env python3
"""Render an OKF knowledge base into a static site.

Mirrors report/render.py in freeunitorg/benchmarks-drupal: standard library
only, every byte of output derived from committed files, no number typed in by
hand.  The markdown on disk stays the source of truth.

Usage: render.py <kb-root> <out-dir>

What it produces in <out-dir>:
  index.html            the entry point, built from <kb-root>/index.md
  <slug>.html           one page per document
  search.json           an inverted index over the body text
  assets/kb.css         styles
  assets/kb.js          client-side search, no dependency
  .nojekyll             stop GitHub Pages from eating files it thinks are special

Why one page per document rather than one long page: the original OKF root has
135 documents at ~880 KB of content, and its own index dangles.  One page per
document keeps a URL per fact, so a review can cite one, and keeps the browser
from loading the whole corpus to read one entry.

Why the frontmatter is rendered as a banner rather than hidden: status and
verified_at are quality signals.  A fact whose status is not "verified" is a
lead, not evidence, and the page has to say so where a reader cannot miss it.
"""
import html
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?", re.S)
# Only the shapes that actually occur in OKF files: scalar, inline list, and a
# block list of scalars or of small maps.  A YAML library would be a dependency
# for no gain here, and a silent misparse is the failure this tool exists to
# prevent, so anything unrecognised is kept verbatim under "_raw".
SCALAR = re.compile(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$")
LIST_ITEM = re.compile(r"^[ \t]+-[ \t]*(.*)$")
MAP_ITEM = re.compile(r"^[ \t]+([A-Za-z_][\w-]*):[ \t]*(.*)$")

UNVERIFIED = {"proposed", "stale", "disputed", "superseded"}

# The publish policy lives in publish.json, so the decision is reviewable and
# diffable rather than buried here.  These constants are only the fallback the
# doc_type lookup uses when no policy is loaded; main() always loads one.
PUBLISH_AREAS = {
    "engineering": "concept",
    "releases": "release",
    "v1": "concept",
    "v2": "concept",
}
# Loose files at the root are named one by one.  team.md is absent on purpose:
# it carries e-mail addresses and is not engineering content.
PUBLISH_ROOT = {
    "history": "history",
    "repos": "reference",
}
# The bold labels the 130 frontmatter-less documents use instead of metadata.
LEGACY_LABEL = re.compile(r"^\*\*(?P<key>[A-Za-z][\w /-]*):\*\*\s*(?P<value>.+?)\s*$")


def doc_type(slug, policy=None):
    """The type comes from where a document lives when the document does not say.

    OKF makes `type` the one required field, but in the real KB only 23 of 153
    documents carry frontmatter and the rest open with a bold-labelled header.
    Requiring the field would reject 85 percent of a KB that is maintained by
    hand, so the area supplies the type and frontmatter overrides it.  A slug
    no rule covers is not published, which is the safe direction to fail.
    """
    areas = (policy or {}).get("areas", PUBLISH_AREAS)
    root_files = (policy or {}).get("root_files", PUBLISH_ROOT)
    if "/" in slug:
        return areas.get(slug.split("/", 1)[0])
    return root_files.get(slug)


def legacy_labels(body):
    """Read the **Key:** value header that a frontmatter-less document opens with.

    Only the leading lines are examined: the same bold label further down the
    body is prose, not metadata.
    """
    found = {}
    for line in body.splitlines()[:15]:
        match = LEGACY_LABEL.match(line)
        if match:
            found[match.group("key").strip().lower()] = match.group("value")
    return found


def load_policy(path):
    """Read the publish policy.  Missing file is fatal: defaulting an allowlist
    would publish whatever the fallback happened to name."""
    try:
        with open(path, encoding="utf-8") as handle:
            policy = json.load(handle)
    except FileNotFoundError:
        print(f"render: no publish policy at {path}", file=sys.stderr)
        raise SystemExit(2)
    except json.JSONDecodeError as error:
        print(f"render: {path} is not valid JSON: {error}", file=sys.stderr)
        raise SystemExit(2)
    return policy


def exclusion_reason(slug, body, policy):
    """Why this document is excluded, or None.

    Two stages, deliberately separate.  The area allowlist decides what may be
    read at all; this decides what is dropped after that, and its reasons are
    printed so a reader can audit the choice instead of trusting it.
    """
    rule = policy.get("exclude", {})
    for entry in rule.get("slug", []):
        if slug == entry:
            return f"slug {entry}"
    for entry in rule.get("subject", []):
        hits = len(re.findall(entry["pattern"], body))
        if hits >= entry.get("min_hits", 1):
            return (f"{hits} x /{entry['pattern']}/ "
                    f"(min {entry.get('min_hits', 1)})")
    return None


def url_for(slug):
    """Directory-style URL, unique per slug and readable when cited.

    GitHub Pages serves <dir>/index.html for /<dir>/, so a document at
    facts/build/x.md becomes facts/build/x/ and links stay clean.  The depth
    also keeps the page's relative asset links working, which a flat scheme
    cannot do once documents stop all sitting at one level.
    """
    return slug + "/index.html"


def parse_scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    if text in ("null", "~", ""):
        return "" if text == "" else None
    if text in ("true", "false"):
        return text == "true"
    return text


def parse_frontmatter(text):
    """Return (metadata dict, body).  Unparsable frontmatter raises: a document
    whose type cannot be read has no place in the KB."""
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta, key, items = {}, None, None
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        scalar = SCALAR.match(line)
        if scalar and not line.startswith((" ", "\t")):
            key, value = scalar.group(1), scalar.group(2)
            if value.strip() in ("", ">-", "|", ">") :
                meta[key] = [] if value.strip() in ("", ">-") else ""
                items = meta[key] if isinstance(meta[key], list) else None
            else:
                meta[key] = parse_scalar(value)
                items = None
            continue
        entry = LIST_ITEM.match(line) if items is not None else None
        if entry is not None:
            items.append(parse_scalar(entry.group(1)))
            continue
        sub = MAP_ITEM.match(line) if items is not None else None
        if sub is not None:
            # a block list of maps: attach to the last item
            if not items or not isinstance(items[-1], dict):
                items.append({})
            items[-1][sub.group(1)] = parse_scalar(sub.group(2))
            continue
        meta.setdefault("_raw", []).append(line)
    return meta, text[match.end():]


def inline(text):
    """Escape first, then re-introduce the markup OKF files actually use."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    # A bare path or SHA in prose is a citation, not decoration.  Linking it
    # would need the repo pinned per document, so leave it as text.
    return out


def markdown(text):
    """A small renderer for the subset OKF documents use: headings, paragraphs,
    fenced and indented code, lists, tables, blockquotes, rules."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>"
                       + html.escape("\n".join(block)) + "</code></pre>")
            continue

        if re.match(r"^\s*\|.*\|\s*$", line) and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>"
                       + "".join(f"<th>{inline(c)}</th>" for c in head)
                       + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>"
                                                  for c in row) + "</tr>"
                                 for row in rows)
                       + "</tbody></table>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^\s*([-*_])\s*\1\s*\1[\s\1]*$", line):
            out.append("<hr>")
            i += 1
            continue

        bullet = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if bullet:
            ordered = bullet.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines):
                item = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[i])
                if not item:
                    break
                items.append(f"<li>{inline(item.group(3))}</li>")
                i += 1
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + markdown("\n".join(quote))
                       + "</blockquote>")
            continue

        if not stripped:
            i += 1
            continue

        para = []
        while i < len(lines) and lines[i].strip() \
                and not re.match(r"^(#{1,6}\s|```|\s*[-*+]\s|\s*\d+\.\s|>|\s*\|)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if not para:
            # A line that stops the loop above but matched none of the earlier
            # branches.  A single pipe line does exactly this: the table branch
            # needs a separator row to claim it, the stop pattern below refuses
            # it, so para stays empty and i never moves.  Emitting the line as
            # its own paragraph and advancing is the only safe move; without it
            # this function never returns and the whole build hangs.
            out.append("<p>" + inline(lines[i].strip()) + "</p>")
            i += 1
            continue
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    return "\n".join(out)


def status_banner(meta):
    """The one thing a reader must not miss.  Nothing is rendered as accepted
    evidence by default."""
    status = meta.get("status")
    if not status:
        return ""
    sha = meta.get("verified_at") or ""
    short = sha[:8] if isinstance(sha, str) else ""
    if status == "verified":
        detail = f" at <code>{html.escape(short)}</code>" if short else ""
        return (f'<p class="banner ok">verified{detail}</p>')
    if status in UNVERIFIED:
        return (f'<p class="banner warn"><strong>{html.escape(status)}</strong> '
                f'&mdash; this is a lead, not evidence. Re-derive it before '
                f'you rely on it.</p>')
    return f'<p class="banner warn">{html.escape(status)}</p>'


def meta_table(meta):
    skip = {"type", "title", "status", "_raw"}
    rows = []
    for key, value in meta.items():
        if key in skip or value in ("", None, []):
            continue
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                rendered = "<br>".join(
                    " ".join(f"{k}={v}" for k, v in item.items())
                    for item in value)
            else:
                rendered = ", ".join(str(v) for v in value)
        else:
            rendered = str(value)
        rows.append(f"<tr><th>{html.escape(key)}</th>"
                    f"<td>{inline(rendered)}</td></tr>")
    if not rows:
        return ""
    return '<table class="meta">' + "".join(rows) + "</table>"


CSS = """\
:root { color-scheme: light dark; }
body { max-width: 52rem; margin: 2rem auto; padding: 0 1rem;
       font: 16px/1.6 system-ui, sans-serif; }
nav.crumbs { font-size: .9rem; opacity: .8; margin-bottom: 1rem; }
h1, h2, h3 { line-height: 1.25; }
pre { background: rgba(127,127,127,.12); padding: .8rem; overflow-x: auto; }
code { background: rgba(127,127,127,.12); padding: .1rem .3rem; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid rgba(127,127,127,.35); padding: .3rem .5rem;
         text-align: left; vertical-align: top; }
table.meta th { width: 9rem; }
.banner { padding: .5rem .8rem; border-radius: .3rem; margin: 0 0 1rem; }
.banner.ok { background: rgba(40,160,80,.15); }
.banner.warn { background: rgba(200,140,0,.18); border-left: 4px solid #c88c00; }
#q { width: 100%; padding: .5rem; font-size: 1rem; }
#hits li { margin: .4rem 0; }
#hits .where { opacity: .7; font-size: .85rem; }
"""

JS = """\
// Client-side search over search.json.  No dependency, no network beyond the
// one file, and it works from file:// as well as from GitHub Pages.
let INDEX = null;
const norm = (s) => s.toLowerCase();
async function load() {
  const res = await fetch('search.json');
  INDEX = await res.json();
}
function score(doc, terms) {
  let total = 0;
  for (const term of terms) {
    const tf = doc.tf[term];
    if (!tf) return 0;             // every term must appear
    total += tf * (doc.title.toLowerCase().includes(term) ? 3 : 1);
  }
  return total;
}
function run(query) {
  const hits = document.getElementById('hits');
  const terms = norm(query).split(/\\s+/).filter(Boolean);
  if (!terms.length) { hits.innerHTML = ''; return; }
  const ranked = INDEX.docs
    .map((doc, i) => ({ i, s: score(doc, terms) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, 25);
  hits.innerHTML = ranked.map(({ i }) => {
    const doc = INDEX.docs[i];
    return `<li><a href="${doc.url}">${doc.title}</a>
      <div class="where">${doc.dir} &middot; ${doc.status || 'no status'}</div></li>`;
  }).join('') || '<li>no match</li>';
}
window.addEventListener('DOMContentLoaded', async () => {
  await load();
  const box = document.getElementById('q');
  box.addEventListener('input', () => run(box.value));
  const q = new URLSearchParams(location.search).get('q');
  if (q) { box.value = q; run(q); }
});
"""


def build_index(docs):
    """An inverted index over body text.  This is the piece a real FTS choice
    replaces; it exists so the pipeline has no hole in it, and so the search
    behaviour can be compared against a library later."""
    output = []
    for doc in docs:
        words = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.\-/]*", doc["text"])
        tf = {}
        for word in words:
            key = word.lower()
            tf[key] = tf.get(key, 0) + 1
        output.append({
            "url": doc["url"],
            "title": doc["meta"].get("title") or doc["slug"],
            "dir": os.path.dirname(doc["slug"]) or ".",
            "status": doc["meta"].get("status") or "",
            "tf": tf,
        })
    # A shared vocabulary is what makes this an index rather than a dump: the
    # terms are listed once and the per-document maps refer to them.
    vocabulary = sorted({term for doc in output for term in doc["tf"]})
    return {"vocabulary": vocabulary, "docs": output}


def render_doc(doc, base, published=None):
    slug = doc["slug"]
    body, withheld = rewrite_links(doc["body"], slug, published or {slug}, base)
    if withheld:
        print(f"render: {slug}: {len(withheld)} link(s) not published "
              f"({', '.join(sorted(withheld)[:2])})", file=sys.stderr)
    body = markdown(body)
    title = doc["meta"].get("title") or slug
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{base}assets/kb.css">
</head><body>
<nav class="crumbs"><a href="{base}index.html">index</a> / {html.escape(slug)}</nav>
{status_banner(doc["meta"])}
<h1>{html.escape(title)}</h1>
{meta_table(doc["meta"])}
{body}
<script src="{base}assets/kb.js"></script>
</body></html>
"""


def rewrite_links(body, slug, published, base):
    """Point a document's own markdown links at generated pages.

    Two reasons this is not optional.  A link to another document uses OKF's
    extension-less form (`../strategy/foo`), which does not resolve to a page,
    so leaving it alone produces a broken link.  And a link can point into an
    area this build does not publish: rewriting it to the withheld placeholder
    is what stops a private path from being advertised in the HTML, which is a
    leak rather than a cosmetic fault.  Anchors, absolute URLs and anything with
    a scheme are left untouched.
    """
    here = os.path.dirname(slug)

    def link(match):
        target = match.group(1)
        if target.startswith(("#", "/", "http://", "https://", "mailto:")):
            return f"]({target})"
        path, _, fragment = target.partition("#")
        if not path:
            return f"]({target})"
        path = path[:-3] if path.endswith(".md") else path
        # Relative first, then as a root-relative path, which is how the real
        # KB writes cross-area links.
        for candidate in (os.path.normpath(os.path.join(here, path)), path):
            candidate = candidate.replace(os.sep, "/").lstrip("./")
            if candidate in published:
                tail = f"#{fragment}" if fragment else ""
                return f"]({base}{url_for(candidate)}{tail})"
        withheld.add(candidate)
        return f"]({base}withheld.html)"

    withheld = set()
    return re.sub(r"\]\(([^)\s]+)\)", link, body), withheld


def write_page(doc, out, base, state, frozen, published):
    """Render one document and record it, without touching the plan.

    Kept separate so the same code path serves a whole build and a sliced one.
    """
    target = os.path.join(out, doc["url"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(render_doc(doc, base, published))
    if state is not None:
        state.setdefault("pages", {})[doc["slug"]] = doc["render_id"]
        state["frozen"] = frozen


def write_assets(out, base):
    os.makedirs(os.path.join(out, "assets"), exist_ok=True)
    open(os.path.join(out, "assets/kb.css"), "w").write(CSS)
    open(os.path.join(out, "assets/kb.js"), "w").write(JS)
    open(os.path.join(out, ".nojekyll"), "w").close()


def write_index_page(out, base, index_md, docs):
    """The entry point, from the KB's own index.md.

    A link to a document that is not published is dropped rather than left
    dangling: the real index lists strategy documents, and an entry pointing at
    a 404 would both advertise what is withheld and mislead a reader.
    """
    meta, body = index_md
    published = {doc["slug"] for doc in docs}
    withheld, dangling = [], []

    def one_line(line):
        """Resolve the links on one index line, dropping withheld entries.

        Dropping the whole link rather than pointing it at a placeholder is
        deliberate: the anchor text is the document's name, so a rewritten link
        still prints the name of a withheld document on a public page.  A line
        that held nothing else goes too, or the index shows an empty bullet.
        """
        dropped = []

        def link(match):
            text, target = match.group(1), match.group(2)
            if target in published:
                return f"[{text}]({base}{url_for(target)})"
            # Both a withheld document and an entry with no file at all are
            # dropped.  Keeping a placeholder for either one still prints its
            # name here, and a public index should not list documents that are
            # excluded or that do not exist.
            if doc_type(target) is not None:
                dangling.append(target)
            else:
                withheld.append(target)
            dropped.append(target)
            return ""

        line = re.sub(r"\[([^\]]*)\]\(([^)]+)\)", link, line)
        # Collapse the separator left behind by a dropped entry: "name - " is
        # what an index line looks like once its link is gone.
        line = re.sub(r"\s+[-\u2014]\s*$", "", line).rstrip()
        return None if line.strip() in ("", "-", "*") else line

    body = "\n".join(
        kept for kept in (one_line(line) for line in body.splitlines())
        if kept is not None
    )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(meta.get('title') or 'index')}</title>
<link rel="stylesheet" href="{base}assets/kb.css">
</head><body>
<h1>{html.escape(meta.get('title') or 'index')}</h1>
<p><input id="q" type="search" placeholder="search the knowledge base"
          autocomplete="off"></p>
<ul id="hits"></ul>
{markdown(body)}
<script src="{base}assets/kb.js"></script>
</body></html>
"""
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(page)
    # The placeholder the withheld entries point at.  It states the rule rather
    # than leaving a dead link, so a reader who follows one learns why the
    # document is absent instead of assuming the site is broken.
    with open(os.path.join(out, "withheld.html"), "w", encoding="utf-8") as handle:
        handle.write(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Not published</title>
<link rel="stylesheet" href="{base}assets/kb.css">
</head><body>
<nav class="crumbs"><a href="{base}index.html">index</a> / withheld</nav>
<h1>Not published</h1>
<p>This entry is part of the knowledge base but is not in a published area.
The build reads only the areas named in its allowlist, so the document was
never opened.</p>
</body></html>
""")
    if withheld:
        print(f"render: index lists {len(withheld)} documents in areas this "
              f"build does not publish", file=sys.stderr)
    if dangling:
        print(f"render: index lists {len(dangling)} documents that do not "
              f"exist: {', '.join(sorted(dangling)[:3])}"
              f"{' ...' if len(dangling) > 3 else ''}", file=sys.stderr)


def collect(root, policy):
    """One pass over the KB.  Returns (docs, index_md, unpublished, excluded).

    This is fast: 0.18 s for 123 documents on the real KB.  The cost that gets
    an invocation killed is rendering and writing the pages, which is why the
    page loop can be sliced while this stays whole.
    """
    docs, index_md = [], None
    unpublished, excluded = [], []
    # The walk variable must not be named "base": that holds the URL prefix,
    # and a loop target rebinding it silently prefixes every asset path with
    # the last directory walked.
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))]
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            slug = rel[:-3]
            if slug == "index":
                index_md = parse_frontmatter(open(path, encoding="utf-8").read())
                continue
            # Check the area before opening the file, so an area the policy does
            # not name is never read into the process at all.
            kind = doc_type(slug, policy)
            if kind is None:
                unpublished.append(slug)
                continue
            text = open(path, encoding="utf-8").read()
            reason = exclusion_reason(slug, text, policy)
            if reason is not None:
                excluded.append((slug, reason))
                continue
            meta, body = parse_frontmatter(text)
            meta.setdefault("type", kind)
            for key, value in legacy_labels(body).items():
                meta.setdefault(key, value)
            docs.append({"slug": slug, "meta": meta, "body": body,
                         "text": body, "url": url_for(slug),
                         "render_id": hashlib.sha256(
                             (slug + "\0" + body).encode()).hexdigest()[:16]})
    return docs, index_md, unpublished, excluded


def build_plan(docs, policy, root):
    """The set of pages a complete build must contain, as a stable JSON object.

    Written before any page is rendered so a build can be split across
    invocations: a later run compares the plan with what is on disk and renders
    only what is missing.  Without this, an interrupted build has to start over,
    and in an environment that kills long invocations it never finishes at all.
    """
    return {
        "kb_root": os.path.abspath(root),
        "policy_areas": sorted(policy.get("areas", {})),
        "documents": [
            {"slug": d["slug"], "url": d["url"], "render_id": d["render_id"],
             "bytes": len(d["body"])}
            for d in sorted(docs, key=lambda d: d["slug"])
        ],
    }


def plan_id(plan):
    """A digest of the plan, so a stale plan is detected instead of trusted."""
    payload = json.dumps(
        [(d["slug"], d["render_id"]) for d in plan["documents"]],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Default the policy next to this script, not next to the caller: CI
    # runs the renderer from the repository root, so a cwd-relative
    # default is a path that depends on how it was invoked.
    base, policy_path, report_only = "/", str(
        pathlib.Path(__file__).resolve().parent / "publish.json"), False
    limit, plan_only = None, False
    state_path = None
    for a in sys.argv[1:]:
        if a.startswith("--base="):
            base = a.split("=", 1)[1]
        elif a.startswith("--policy="):
            policy_path = a.split("=", 1)[1]
        elif a.startswith("--limit="):
            limit = int(a.split("=", 1)[1])
        elif a.startswith("--state="):
            state_path = a.split("=", 1)[1]
        elif a == "--plan":
            plan_only = True
        elif a == "--report":
            report_only = True
    base = base if base.endswith("/") else base + "/"
    root = args[0] if args else "."
    out = args[1] if len(args) > 1 else "public"

    policy = load_policy(policy_path)
    report_only = report_only or bool(policy.get("report_only"))

    docs, index_md, unpublished, excluded = collect(root, policy)

    if unpublished:
        print(f"render: {len(unpublished)} documents in areas the policy does "
              f"not publish, not read: "
              f"{', '.join(sorted({s.split('/')[0] for s in unpublished}))}",
              file=sys.stderr)
    if excluded:
        print(f"render: {len(excluded)} documents excluded by policy:",
              file=sys.stderr)
        for slug, reason in sorted(excluded):
            print(f"    {slug}: {reason}", file=sys.stderr)
    if report_only:
        print(f"render: --report, {len(docs)} documents would be published",
              file=sys.stderr)
        return 0

    if not docs:
        print(f"render: no documents under {root}", file=sys.stderr)
        return 2
    if index_md is None:
        print("render: no index.md, the site has no entry point",
              file=sys.stderr)
        return 2

    # A flat URL scheme silently loses a document when two areas use the same
    # filename, which real OKF roots do (engineering/status.md and v1/status.md
    # would both become status.html).  Flattening is only safe if it is proven
    # unique, so prove it and stop otherwise.  GitHub Pages serves a directory
    # index, so <slug>/index.html keeps the URL readable and stays unique.
    seen = {}
    for doc in docs:
        if doc["url"] in seen:
            print(f"render: {doc['slug']} and {seen[doc['url']]} both map to "
                  f"{doc['url']}", file=sys.stderr)
            return 2
        seen[doc["url"]] = doc["slug"]

    plan = build_plan(docs, policy, root)
    digest = plan_id(plan)
    state_file = state_path or os.path.join(out, os.pardir, ".build-state.json")

    # The plan is written first, so an interrupted build can resume against it
    # and a later run can tell whether the KB changed underneath.
    os.makedirs(out, exist_ok=True)
    write_assets(out, base)
    with open(os.path.join(out, os.pardir, "plan.json"), "w", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=1, sort_keys=True)
    if plan_only:
        print(f"render: --plan, {len(docs)} documents, plan {digest}")
        return 0

    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, encoding="utf-8") as handle:
                state = json.load(handle)
        except json.JSONDecodeError:
            state = {}
    if state.get("plan") != digest:
        # A different KB or policy: the recorded pages describe a build that no
        # longer matches, so start clean rather than resume into a mixture.
        state = {}
    done = state.get("pages", {})
    pending = [d for d in docs if done.get(d["slug"]) != d["render_id"]]

    published = {d["slug"] for d in docs}
    slice_ = pending if limit is None else pending[:limit]
    for doc in slice_:
        write_page(doc, out, base, state, digest, published)
        state.setdefault("pages", {})[doc["slug"]] = doc["render_id"]
    state["plan"] = digest

    remaining = len(pending) - len(slice_)
    print(f"render: plan {digest}, {len(docs)} documents, "
          f"{len(docs) - len(pending)} already present, wrote {len(slice_)}, "
          f"{remaining} remaining", file=sys.stderr)

    with open(state_file, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=1, sort_keys=True)

    if remaining:
        return 0

    # The index page and the search index come last, once every document page
    # exists, so neither is ever built against a partial tree.
    write_index_page(out, base, index_md, docs)
    index = build_index(docs)
    with open(os.path.join(out, "search.json"), "w", encoding="utf-8") as handle:
        json.dump(index, handle, separators=(",", ":"), sort_keys=True)
    print(f"render: complete, {len(docs)} documents -> {out}")
    print(f"render: search.json "
          f"{os.path.getsize(os.path.join(out,'search.json'))} bytes, "
          f"{len(index['vocabulary'])} terms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
