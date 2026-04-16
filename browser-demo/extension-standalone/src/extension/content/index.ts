type ContentMessage = { type: 'GET_PAGE_SNAPSHOT' };

function isHidden(el: Element): boolean {
  const h = el as HTMLElement;
  const style = window.getComputedStyle(h);
  return (
    h.hidden ||
    style.display === 'none' ||
    style.visibility === 'hidden' ||
    Number(style.opacity) === 0 ||
    h.getAttribute('aria-hidden') === 'true'
  );
}

function collectHiddenSignals(): string[] {
  const signals: string[] = [];
  const hiddenEls = Array.from(document.querySelectorAll('*')).filter(isHidden).slice(0, 30);
  for (const el of hiddenEls) {
    const text = (el.textContent || '').trim();
    if (text && text.length > 4) signals.push(`hidden_dom:${text.slice(0, 120)}`);
    const aria = el.getAttribute('aria-label');
    if (aria) signals.push(`aria_label:${aria.slice(0, 120)}`);
  }

  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_COMMENT);
  let node = walker.nextNode();
  while (node && signals.length < 60) {
    const v = (node.nodeValue || '').trim();
    if (v) signals.push(`comment:${v.slice(0, 120)}`);
    node = walker.nextNode();
  }

  const body = document.body?.innerText || '';
  if (/[\u200B-\u200D\uFEFF]/.test(body)) {
    signals.push('zero_width_chars_detected');
  }

  return signals;
}

function getSnapshot() {
  const visibleText = document.body?.innerText || '';
  const rawText = document.body?.textContent || '';
  const links = Array.from(document.querySelectorAll('a[href]')).map((a) => ({
    text: (a.textContent || '').trim(),
    href: (a as HTMLAnchorElement).href
  }));

  return {
    url: window.location.href,
    title: document.title,
    visibleText,
    rawText,
    hiddenSignals: collectHiddenSignals(),
    links
  };
}

chrome.runtime.onMessage.addListener((msg: ContentMessage, _sender, sendResponse) => {
  if (msg.type === 'GET_PAGE_SNAPSHOT') {
    sendResponse(getSnapshot());
  }
});
