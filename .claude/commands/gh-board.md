---
name: gh-board
description: Show GitHub Project board status and identify stale or missing updates
---

Audit the Agent Hypervisor GitHub Project board (project #7, owner sv-pro).

Steps:
1. List all project items with current board status:
   ```bash
   gh project item-list 7 --owner sv-pro --limit 50 --format json
   ```
2. Cross-reference each item against actual GitHub issue state (open/closed):
   ```bash
   gh issue list --repo sv-pro/agent-hypervisor --state all --limit 50 --json number,title,state
   ```
3. Report:
   - Items closed on GitHub but not marked Done on board
   - Items marked Done on board but still open on GitHub
   - Any duplicate titles
   - Items with no status set (—) that appear implemented

Issue → milestone mapping:
- M2 Core Engine: #10–17
- M3 Tool Boundary: #18–23
- M4 Proof: #24–30
- M5 Beta Product: #31–34

Project node ID: `PVT_kwHOBrldms4BREso`
Status field ID: `PVTSSF_lAHOBrldms4BREsozg_Ajso`
Done option ID: `98236657`
