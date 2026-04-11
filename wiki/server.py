"""
wiki/server.py — Agent Hypervisor Wiki browser.

Serves the wiki/ directory as an in-browser documentation site.
Markdown is rendered client-side (marked.js) so no extra Python deps are needed.

Usage:
    python wiki/server.py
    # → http://localhost:7777

Or from the repo root:
    uvicorn wiki.server:app --reload --port 7777
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

WIKI_ROOT = Path(__file__).parent          # wiki/
STATIC_DIR = WIKI_ROOT / "_static"        # wiki/_static/   (our SPA assets)
STATIC_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Agent Hypervisor Wiki", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# API: walk the wiki tree and return a navigation tree
# ---------------------------------------------------------------------------

_SKIP = {"_static", "_research"}   # collapse these in nav (still accessible)
_ORDER = ["index.md", "concepts", "comparisons", "scenarios", "code", "log.md"]


def _md_title(path: Path) -> str:
    """Read the first H1 from a markdown file as its display title."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    # Fall back to prettified filename
    return path.stem.replace("-", " ").replace("_", " ").title()


def _build_tree(root: Path, rel: Path | None = None) -> list:
    """Recursively build a nav tree for the given directory."""
    if rel is None:
        rel = Path(".")
    entries = []
    try:
        children = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return []

    # Reorder: prioritise _ORDER items at top
    def _sort_key(p: Path) -> tuple:
        name = p.name
        if name in _ORDER:
            return (0, _ORDER.index(name), name)
        return (1, 999, name)

    children = sorted(children, key=_sort_key)

    for child in children:
        if child.name.startswith(".") or child.name == "_static" or child.name == "server.py":
            continue
        child_rel = rel / child.name
        if child.is_dir():
            subtree = _build_tree(child, child_rel)
            entries.append({
                "type": "dir",
                "name": child.name,
                "path": str(child_rel),
                "label": child.name.replace("-", " ").replace("_", " ").title(),
                "collapsed": child.name.startswith("_"),
                "children": subtree,
            })
        elif child.suffix == ".md":
            entries.append({
                "type": "file",
                "name": child.name,
                "path": str(child_rel),
                "label": _md_title(child),
            })
        elif child.suffix == ".txt" and child.name != "PROMPT.txt":
            entries.append({
                "type": "file",
                "name": child.name,
                "path": str(child_rel),
                "label": child.stem.replace("-", " ").title(),
            })
    return entries


@app.get("/api/tree")
def api_tree() -> JSONResponse:
    """Return the full wiki nav tree as JSON."""
    return JSONResponse(_build_tree(WIKI_ROOT))


@app.get("/api/page")
def api_page(path: str = "index.md") -> JSONResponse:
    """
    Return the raw markdown content (+ metadata) for a wiki page.

    Query param:
        path — relative path from wiki root, e.g. "concepts/architecture.md"
    """
    # Sanitise: no traversal outside wiki root
    try:
        target = (WIKI_ROOT / path).resolve()
        target.relative_to(WIKI_ROOT.resolve())
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Page not found: {path}")

    if target.is_dir():
        # Try index.md inside the dir
        index = target / "index.md"
        if index.exists():
            target = index
        else:
            # Synthesise a listing page
            listing = f"# {target.name.replace('-', ' ').title()}\n\n"
            for child in sorted(target.iterdir()):
                if child.suffix == ".md":
                    rel = child.relative_to(WIKI_ROOT)
                    listing += f"- [{_md_title(child)}]({rel})\n"
            return JSONResponse({"path": path, "content": listing, "title": target.name})

    text = target.read_text(encoding="utf-8", errors="replace")
    # Rewrite relative markdown links so the SPA can intercept them
    title = _md_title(target)
    parent_dir = target.parent.relative_to(WIKI_ROOT)
    text = _rewrite_links(text, parent_dir)
    return JSONResponse({"path": path, "content": text, "title": title})


def _rewrite_links(text: str, base: Path) -> str:
    """
    Rewrite relative markdown links [label](relative/path.md) so that the SPA
    receives them as wiki-root-relative paths (no leading slash).
    Absolute URLs (http/https/#) are left unchanged.
    """
    def _sub(m: re.Match) -> str:
        label = m.group(1)
        href = m.group(2)
        if href.startswith(("http", "#", "/")):
            return m.group(0)
        resolved = (base / href).as_posix()
        # Normalise: remove any leading "./"
        resolved = resolved.lstrip("./")
        if resolved.startswith("./"):
            resolved = resolved[2:]
        return f"[{label}]({resolved})"

    return re.sub(r"\[([^\]]*)\]\(([^)]+)\)", _sub, text)


# ---------------------------------------------------------------------------
# SPA shell (inline — no build step needed)
# ---------------------------------------------------------------------------

_SPA_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Agent Hypervisor Wiki</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
:root {
  --bg:        #0d1117;
  --bg-panel:  #161b22;
  --bg-hover:  #1c2230;
  --border:    #30363d;
  --text:      #e6edf3;
  --muted:     #768390;
  --accent:    #58a6ff;
  --accent2:   #3fb950;
  --tag-bg:    #1f2937;
  --code-bg:   #161b22;
  --sidebar-w: 280px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: 'Inter', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  display: flex;
  height: 100vh;
}

/* ── Sidebar ── */
#sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  height: 100vh;
  overflow-y: auto;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
#sidebar-header {
  padding: 20px 16px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
#sidebar-header h1 {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .5px;
  text-transform: uppercase;
  color: var(--muted);
}
#sidebar-header .logo {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
#sidebar-header .logo svg { flex-shrink: 0; }
#search-wrap { padding: 10px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
#search {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  color: var(--text);
  font-size: 13px;
  outline: none;
  transition: border-color .15s;
}
#search::placeholder { color: var(--muted); }
#search:focus { border-color: var(--accent); }
#nav { flex: 1; padding: 8px 0; }
.nav-section { }
.nav-dir-label {
  display: flex; align-items: center; justify-content: space-between;
  padding: 5px 12px 5px 14px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .5px;
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  border-radius: 4px;
  margin: 2px 4px;
  transition: color .15s;
}
.nav-dir-label:hover { color: var(--text); background: var(--bg-hover); }
.nav-dir-label .caret { transition: transform .2s; font-size: 10px; }
.nav-dir-label.open .caret { transform: rotate(90deg); }
.nav-dir-children { padding-left: 10px; }
.nav-dir-children.collapsed { display: none; }
.nav-item {
  display: block;
  padding: 5px 12px 5px 14px;
  margin: 1px 4px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background .1s, color .1s;
}
.nav-item:hover { background: var(--bg-hover); color: var(--text); }
.nav-item.active { background: #1a3a5c; color: var(--accent); font-weight: 500; }
.nav-item.hidden { display: none; }

/* ── Main ── */
#main {
  flex: 1;
  height: 100vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
#topbar {
  padding: 12px 36px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex; align-items: center; gap: 8px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--muted);
}
#topbar .crumb { cursor: pointer; }
#topbar .crumb:hover { color: var(--accent); }
#topbar .sep { opacity: .4; }
#content {
  flex: 1;
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
  padding: 44px 36px 80px;
}
#loading { text-align: center; color: var(--muted); padding: 80px 0; font-size: 14px; }

/* ── Markdown rendering ── */
#article h1 { font-size: 28px; font-weight: 700; margin-bottom: 24px; color: var(--text); line-height: 1.25; }
#article h2 { font-size: 20px; font-weight: 600; margin: 36px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); color: var(--text); }
#article h3 { font-size: 16px; font-weight: 600; margin: 24px 0 8px; color: var(--text); }
#article h4 { font-size: 14px; font-weight: 600; margin: 16px 0 6px; color: var(--muted); text-transform: uppercase; letter-spacing: .4px; }
#article p { font-size: 14.5px; line-height: 1.8; color: #c9d1d9; margin-bottom: 14px; }
#article a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; transition: border-color .15s; }
#article a:hover { border-bottom-color: var(--accent); }
#article ul, #article ol { padding-left: 22px; margin-bottom: 14px; }
#article li { font-size: 14.5px; line-height: 1.75; color: #c9d1d9; margin-bottom: 4px; }
#article li p { margin-bottom: 4px; }
#article code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px;
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
  color: #ffa657;
}
#article pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  overflow-x: auto;
  margin-bottom: 18px;
}
#article pre code {
  background: transparent;
  border: none;
  padding: 0;
  color: #e6edf3;
  font-size: 13px;
  line-height: 1.6;
}
#article blockquote {
  border-left: 3px solid var(--accent);
  padding: 8px 16px;
  margin: 0 0 14px;
  background: var(--bg-panel);
  border-radius: 0 6px 6px 0;
}
#article blockquote p { margin: 0; color: var(--muted); }
#article table { width: 100%; border-collapse: collapse; margin-bottom: 18px; font-size: 13.5px; }
#article th { background: var(--bg-panel); padding: 8px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid var(--border); color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .4px; }
#article td { padding: 8px 12px; border-bottom: 1px solid var(--border); color: #c9d1d9; vertical-align: top; }
#article tr:hover td { background: var(--bg-panel); }
#article hr { border: none; border-top: 1px solid var(--border); margin: 28px 0; }
#article img { max-width: 100%; border-radius: 6px; }

/* ── Empty / 404 state ── */
#empty { text-align: center; color: var(--muted); padding: 80px 0; }
#empty h2 { font-size: 20px; margin-bottom: 8px; }
#empty p { font-size: 14px; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Resize handle ── */
#resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
  transition: background .2s;
}
#resize-handle:hover { background: var(--accent); }

@media (max-width: 680px) {
  #sidebar { display: none; }
}
</style>
</head>
<body>

<aside id="sidebar">
  <div id="sidebar-header">
    <div class="logo">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" stroke-width="2">
        <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
      </svg>
      Agent Hypervisor
    </div>
    <h1>Wiki</h1>
  </div>
  <div id="search-wrap">
    <input id="search" type="search" placeholder="Search pages…" autocomplete="off"/>
  </div>
  <nav id="nav">Loading…</nav>
</aside>

<div id="resize-handle"></div>

<main id="main">
  <div id="topbar"><span id="breadcrumb"></span></div>
  <div id="content">
    <div id="loading">Loading…</div>
    <div id="article" style="display:none"></div>
    <div id="empty" style="display:none"><h2>Page not found</h2><p>The requested page does not exist.</p></div>
  </div>
</main>

<script>
// ── marked config ──────────────────────────────────────────────────────────
marked.setOptions({ gfm: true, breaks: false });

// ── State ─────────────────────────────────────────────────────────────────
let navTree = [];
let currentPath = 'index.md';

// ── Nav tree rendering ─────────────────────────────────────────────────────
function renderNav(tree, container, query) {
  container.innerHTML = '';
  for (const node of tree) {
    if (node.type === 'dir') {
      const wrap = document.createElement('div');
      wrap.className = 'nav-section';
      const label = document.createElement('div');
      label.className = 'nav-dir-label' + (node.collapsed ? '' : ' open');
      label.innerHTML = `<span>${node.label}</span><span class="caret">▶</span>`;
      const children = document.createElement('div');
      children.className = 'nav-dir-children' + (node.collapsed ? ' collapsed' : '');
      renderNav(node.children, children, query);
      label.addEventListener('click', () => {
        label.classList.toggle('open');
        children.classList.toggle('collapsed');
      });
      // Auto-expand when searching
      if (query && children.querySelector('.nav-item:not(.hidden)')) {
        label.classList.add('open');
        children.classList.remove('collapsed');
      }
      wrap.appendChild(label);
      wrap.appendChild(children);
      container.appendChild(wrap);
    } else {
      const item = document.createElement('div');
      item.className = 'nav-item';
      item.textContent = node.label;
      item.dataset.path = node.path;
      if (query && !node.label.toLowerCase().includes(query.toLowerCase())) {
        item.classList.add('hidden');
      }
      if (node.path === currentPath) item.classList.add('active');
      item.addEventListener('click', () => loadPage(node.path));
      container.appendChild(item);
    }
  }
}

function flatItems(tree) {
  const items = [];
  for (const n of tree) {
    if (n.type === 'file') items.push(n);
    else items.push(...flatItems(n.children));
  }
  return items;
}

// ── Page loading ───────────────────────────────────────────────────────────
async function loadPage(path) {
  currentPath = path;
  history.replaceState({path}, '', '#' + path);

  document.getElementById('loading').style.display = 'block';
  document.getElementById('article').style.display = 'none';
  document.getElementById('empty').style.display = 'none';

  try {
    const r = await fetch('/api/page?path=' + encodeURIComponent(path));
    if (!r.ok) throw new Error('not found');
    const data = await r.json();

    document.title = data.title + ' — Agent Hypervisor Wiki';
    updateBreadcrumb(path, data.title);

    const html = marked.parse(data.content);
    const article = document.getElementById('article');
    article.innerHTML = html;
    article.style.display = 'block';
    document.getElementById('loading').style.display = 'none';

    // Intercept internal links
    article.querySelectorAll('a').forEach(a => {
      const href = a.getAttribute('href');
      if (!href || href.startsWith('http') || href.startsWith('#')) return;
      a.addEventListener('click', e => {
        e.preventDefault();
        loadPage(href);
      });
    });

    // Scroll to top
    document.getElementById('main').scrollTo(0, 0);
  } catch {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('empty').style.display = 'block';
  }

  // Update nav highlight
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.path === path);
  });
  // Scroll active nav item into view
  const active = document.querySelector('.nav-item.active');
  if (active) active.scrollIntoView({block: 'nearest'});
}

function updateBreadcrumb(path, title) {
  const parts = path.split('/');
  const bc = document.getElementById('breadcrumb');
  bc.innerHTML = '';
  let built = '';
  parts.forEach((p, i) => {
    built += (i ? '/' : '') + p;
    const isLast = i === parts.length - 1;
    const label = isLast ? title : p.replace(/[-_]/g, ' ');
    const span = document.createElement('span');
    if (!isLast) {
      span.className = 'crumb';
      span.textContent = label;
      const captured = built;
      span.addEventListener('click', () => loadPage(captured));
      bc.appendChild(span);
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = ' / ';
      bc.appendChild(sep);
    } else {
      span.textContent = label;
      span.style.color = 'var(--text)';
      bc.appendChild(span);
    }
  });
}

// ── Search ─────────────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', function() {
  const q = this.value.trim();
  renderNav(navTree, document.getElementById('nav'), q);
});

// ── Resize handle ──────────────────────────────────────────────────────────
const handle = document.getElementById('resize-handle');
const sidebar = document.getElementById('sidebar');
let resizing = false, startX = 0, startW = 0;
handle.addEventListener('mousedown', e => {
  resizing = true; startX = e.clientX; startW = sidebar.offsetWidth;
  document.body.style.userSelect = 'none';
});
document.addEventListener('mousemove', e => {
  if (!resizing) return;
  const w = Math.max(180, Math.min(480, startW + e.clientX - startX));
  sidebar.style.width = sidebar.style.minWidth = w + 'px';
});
document.addEventListener('mouseup', () => {
  resizing = false;
  document.body.style.userSelect = '';
});

// ── Boot ───────────────────────────────────────────────────────────────────
async function boot() {
  const r = await fetch('/api/tree');
  navTree = await r.json();
  const nav = document.getElementById('nav');
  renderNav(navTree, nav, '');

  // Honour URL hash
  const hash = location.hash.slice(1);
  const startPath = hash || 'index.md';
  loadPage(startPath);
}

window.addEventListener('popstate', e => {
  if (e.state?.path) loadPage(e.state.path);
});

boot();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def spa_root() -> HTMLResponse:
    return HTMLResponse(_SPA_HTML)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7777, log_level="warning")
