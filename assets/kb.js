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
  const terms = norm(query).split(/\s+/).filter(Boolean);
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
