/**
 * Content script — runs in every page context (document_idle).
 *
 * Responsibilities:
 *  1. Extract visible page text
 *  2. Detect hidden content (CSS hidden, aria-hidden, zero-width chars, comments)
 *  3. Compute a lightweight content fingerprint
 *  4. Send PageSnapshot to the background service worker
 */

import type { PageSnapshot } from "../types";

// ---------------------------------------------------------------------------
// Text extraction
// ---------------------------------------------------------------------------

function extractVisibleText(): string {
  const bodyText = document.body?.innerText ?? "";
  return bodyText.slice(0, 4000).trim(); // cap to avoid huge messages
}

// ---------------------------------------------------------------------------
// Hidden content detection
// ---------------------------------------------------------------------------

interface HiddenDetectionResult {
  detected: boolean;
  summary: string | null;
}

function detectHiddenContent(): HiddenDetectionResult {
  const signals: string[] = [];

  // 1. CSS-hidden elements with suspicious text
  const cssHiddenSelectors = [
    "[style*='display:none']",
    "[style*='display: none']",
    "[style*='visibility:hidden']",
    "[style*='visibility: hidden']",
    "[style*='opacity:0']",
    "[style*='opacity: 0']",
    "[hidden]",
  ];
  for (const sel of cssHiddenSelectors) {
    const els = document.querySelectorAll<HTMLElement>(sel);
    els.forEach((el) => {
      const text = el.innerText?.trim() ?? el.textContent?.trim() ?? "";
      if (text.length > 5) {
        signals.push(`CSS-hidden element: "${text.slice(0, 120)}"`);
      }
    });
  }

  // 2. aria-hidden elements with text
  document.querySelectorAll<HTMLElement>('[aria-hidden="true"]').forEach((el) => {
    const text = el.textContent?.trim() ?? "";
    if (text.length > 5) {
      signals.push(`aria-hidden text: "${text.slice(0, 120)}"`);
    }
  });

  // 3. Zero-width / invisible unicode characters in body text
  const bodyText = document.body?.textContent ?? "";
  const zwChars = (bodyText.match(/[\u200B\u200C\u200D\uFEFF]/g) ?? []).length;
  if (zwChars > 0) {
    signals.push(`Zero-width characters detected (${zwChars} occurrences)`);
  }

  // 4. HTML comments with suspiciously long content
  const walker = document.createTreeWalker(
    document.body ?? document.documentElement,
    NodeFilter.SHOW_COMMENT,
  );
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const text = (node.textContent ?? "").trim();
    if (text.length > 20) {
      signals.push(`HTML comment: "${text.slice(0, 120)}"`);
    }
  }

  // 5. Very small font-size (< 2px)
  document.querySelectorAll<HTMLElement>("*").forEach((el) => {
    const fs = parseFloat(window.getComputedStyle(el).fontSize);
    if (fs > 0 && fs < 2) {
      const text = el.textContent?.trim() ?? "";
      if (text.length > 5) {
        signals.push(`Tiny text (${fs}px): "${text.slice(0, 80)}"`);
      }
    }
  });

  // Inject-attempt keywords in combined hidden content
  const combinedSignals = signals.join(" ").toLowerCase();
  const suspiciousKeywords = [
    "agent override",
    "ignore previous",
    "remember this as trusted",
    "export",
    "memory",
    "trusted profile",
    "attacker",
    "webhook",
    "prompt injection",
  ];
  const hasHostileContent = suspiciousKeywords.some((kw) =>
    combinedSignals.includes(kw),
  );

  if (hasHostileContent) {
    signals.unshift("⚠ Hostile instruction keywords detected in hidden content");
  }

  return {
    detected: signals.length > 0,
    summary: signals.length > 0 ? signals.join(" | ") : null,
  };
}

// ---------------------------------------------------------------------------
// Simple hash (not cryptographic — just for change detection)
// ---------------------------------------------------------------------------

function simpleHash(text: string): string {
  let hash = 0;
  for (let i = 0; i < Math.min(text.length, 2000); i++) {
    hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  }
  return "fnv:" + Math.abs(hash).toString(16);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function captureAndSend(): void {
  const visibleText = extractVisibleText();
  const hidden = detectHiddenContent();

  const snapshot: PageSnapshot = {
    source_type: "web_page",
    url: window.location.href,
    title: document.title,
    visible_text: visibleText,
    hidden_content_detected: hidden.detected,
    hidden_content_summary: hidden.summary,
    content_hash: simpleHash(visibleText),
    captured_at: new Date().toISOString(),
  };

  chrome.runtime.sendMessage({ type: "PAGE_CAPTURED", snapshot });
}

// Run on initial load and on SPA navigation
captureAndSend();
