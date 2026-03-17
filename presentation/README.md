# The Missing Layer — Presentation

**Agent Hypervisor: From behavior control to world design for AI agents**

A browser-based slide deck built with [Reveal.js](https://revealjs.com/).
Dark, minimal, architectural. Designed to be shown live, exported to PDF, or iterated in code.

---

## Run locally

### Option A — Direct file open (simplest)

```bash
open presentation/index.html
# or on Linux:
xdg-open presentation/index.html
```

> **Note:** The presentation loads Reveal.js and fonts from CDN.
> An internet connection is required on first open. After the browser caches the assets, it works offline.

---

### Option B — Local static server (recommended for best experience)

Avoids any browser security restrictions on local file access.

**Python (no install required):**
```bash
cd presentation
python3 -m http.server 8000
# Then open: http://localhost:8000
```

**Node (if installed):**
```bash
npx serve presentation
# Then follow the printed URL
```

**VS Code:** Install the "Live Server" extension, right-click `index.html` → *Open with Live Server*.

---

## Navigation

| Action | Keys |
|--------|------|
| Next slide | `→` `Space` `PageDown` |
| Previous slide | `←` `PageUp` |
| Next fragment | `→` `Space` |
| Overview mode | `Esc` or `O` |
| Full screen | `F` |
| Speaker notes | `S` |
| Pause/blackout | `B` or `.` |

---

## Export to PDF

Reveal.js supports native PDF export via Chrome/Chromium print dialog.

1. Open the presentation in Chrome or Chromium
2. Append `?print-pdf` to the URL:
   ```
   http://localhost:8000/?print-pdf
   ```
3. Open **Print** dialog (`Ctrl+P` / `Cmd+P`)
4. Set:
   - Destination: **Save as PDF**
   - Layout: **Landscape**
   - Margins: **None**
   - Background graphics: **enabled**
5. Save

This produces a high-quality PDF with one page per slide.

---

## File structure

```
presentation/
├── index.html      # All 13 slides, Reveal.js init
├── theme.css       # Custom dark theme (full override)
└── README.md       # This file
```

---

## Slides

| # | Title | Key idea |
|---|-------|---------|
| 1 | Title | The Missing Layer |
| 2 | The Pattern | Every AI defense fails for the same reason |
| 3 | The Inversion | Wrong question vs. right question |
| 4 | Bash (broken) | String allowlist is not capability design |
| 5 | Rendered World | The action that cannot be proposed |
| 6 | Email Example | Capability construction removes generality at design-time |
| 7 | Semantic Events | Typed perception, not raw text |
| 8 | 4-Layer Model | The architecture: Physics → Ontology → Rendering → Governance |
| 9 | Rendering Engine | Layer 2 as the central insight |
| 10 | Design-time vs Runtime | Stochastic intelligence belongs at design-time |
| 11 | Full System Flow | The complete runtime pipeline |
| 12 | Why It Matters | Every agentic attack class is one architectural gap |
| 13 | Final Thesis | We do not make agents safe. We make the world they live in safe. |

---

## Customization

- **Colors / fonts:** edit CSS variables at the top of `theme.css`
- **Transitions:** change `transition:` in the `Reveal.initialize({})` call in `index.html`
- **Slide content:** each slide is a `<section>` in `index.html` — edit inline
- **Fragments (click-to-reveal):** elements with `class="fragment"` appear on next keypress
- **Auto-animate:** slides with `data-auto-animate` transition matched elements smoothly

---

## Requirements

- Any modern browser (Chrome, Firefox, Safari, Edge)
- Internet connection for CDN assets (Reveal.js 4.6.1 + Google Fonts)
  — or download Reveal.js locally and update the `<script>` / `<link>` paths

---

*Part of the [Agent Hypervisor](../README.md) project.*
