"""
canonicalizer.py — Input normalization layer for Agent Hypervisor defense.

Strips known injection patterns from tool outputs before the LLM sees them.
This is NOT a semantic filter — it targets the specific syntactic patterns
used by AgentDojo's attack vectors (important_instructions, tool_knowledge,
direct_prompt_injection, etc.).

Key principle: canonicalization is deterministic and LLM-free. The same
input always produces the same output. This makes it auditable.

AgentDojo attack patterns to neutralize:
  - important_instructions: "IMPORTANT!!! Ignore all previous instructions..."
  - tool_knowledge: carefully crafted tool calls embedded in outputs
  - direct injection: "[[SYSTEM: ...]]", "<|system|>", zero-width chars
"""

from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Known injection patterns (compiled once at module load)
# ---------------------------------------------------------------------------

# Zero-width and invisible Unicode codepoints used to hide instructions
_ZERO_WIDTH_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u2028\u2029\u00ad]"
)

# IMPORTANT!!! type prefixes used by AgentDojo's important_instructions attack
_IMPORTANT_PREFIX = re.compile(
    r"(?i)IMPORTANT[!?.\s]*(?:ignore|disregard|forget|override)[^\n]*\n?",
    re.MULTILINE,
)

# System-impersonation markers
_SYSTEM_MARKERS = re.compile(
    r"(?i)\[\[SYSTEM:[^\]]*\]\]|\[SYSTEM\]|<\|system\|>|<system>.*?</system>",
    re.DOTALL,
)

# Injected instruction delimiters seen in real attacks
_INSTRUCTION_BLOCKS = re.compile(
    r"(?i)(?:---+|===+)\s*(?:NEW INSTRUCTIONS?|OVERRIDE|ADMIN|OPERATOR)[^\n]*\n",
    re.MULTILINE,
)

# Fake tool-call injections embedded in text (tool_knowledge attack pattern)
# e.g.: "Please call: send_email(to='attacker@evil.com', ...)"
_FAKE_TOOL_CALLS = re.compile(
    r"(?i)(?:please\s+)?(?:call|execute|run|invoke|use)[:\s]+\w+\s*\([^)]{0,300}\)",
    re.MULTILINE,
)

# Prompt-leak exfiltration patterns
_PROMPT_LEAK_PATTERNS = re.compile(
    r"(?i)(?:repeat|print|output|reveal|show|display)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|context)[^\n]*\n?",
    re.MULTILINE,
)


class Canonicalizer:
    """
    Deterministic input sanitizer for the AH defense pipeline.

    Strips known injection syntax from text strings. Does not use any ML
    or LLM — all rules are regex-based and compile-time constant.

    Usage:
        c = Canonicalizer()
        clean = c.canonicalize(raw_tool_output)
    """

    def __init__(self, aggressive: bool = False) -> None:
        """
        Args:
            aggressive: If True, also strip the fake-tool-call pattern
                (may reduce utility on legitimate outputs that describe
                 function calls in prose). Default: False.
        """
        self.aggressive = aggressive

    def canonicalize(self, text: str) -> str:
        """
        Remove known injection patterns from a string.

        Args:
            text: Raw text from a tool output.

        Returns:
            Sanitized text with injection patterns removed.
        """
        if not text:
            return text

        # Step 1: Normalize Unicode — NFKC eliminates homoglyph attacks
        text = unicodedata.normalize("NFKC", text)

        # Step 2: Strip zero-width / invisible characters
        text = _ZERO_WIDTH_CHARS.sub("", text)

        # Step 3: Remove system-impersonation markers
        text = _SYSTEM_MARKERS.sub("[REDACTED:system-marker]", text)

        # Step 4: Remove IMPORTANT!!! injection prefixes
        text = _IMPORTANT_PREFIX.sub("[REDACTED:injection-prefix]", text)

        # Step 5: Remove instruction-override blocks
        text = _INSTRUCTION_BLOCKS.sub("[REDACTED:instruction-block]", text)

        # Step 6: Remove prompt-leak exfiltration patterns
        text = _PROMPT_LEAK_PATTERNS.sub("[REDACTED:prompt-leak]", text)

        # Step 7 (aggressive only): Remove embedded fake tool call patterns
        if self.aggressive:
            text = _FAKE_TOOL_CALLS.sub("[REDACTED:fake-tool-call]", text)

        return text

    def wrap_with_trust_metadata(self, text: str, source: str = "tool_output") -> str:
        """
        Wrap canonicalized text with AH trust metadata.

        This makes the trust boundary visible to the LLM in the conversation,
        reinforcing the ontological distinction between trusted instructions
        (user query, system prompt) and untrusted data (tool outputs).

        Args:
            text: Canonicalized tool output text.
            source: The source identifier for the data.

        Returns:
            Text wrapped with AH trust envelope.
        """
        return f"[AH|SOURCE:{source}|TRUST:untrusted]\n{text}\n[/AH]"
