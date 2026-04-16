"""
minimizer.py — Deterministic program minimization engine (PL-3).

Converts a raw candidate program (list of CandidateStep) into a minimized
form by applying a fixed set of deterministic reduction rules.

Minimization rules (applied in order):
    1. Consecutive duplicate removal — remove consecutive steps with identical
       tool and params.  Only the first occurrence is kept.
    2. Parameter reduction — within each surviving step's params dict:
       a. Drop keys whose value is None.
       b. Drop keys whose value is "" (empty string).
       c. For URL-type params (key contains "url", value starts with http/https),
          strip query string and fragment if present.
    3. Capability surface reduction — if a step declares a broad capability
       pattern (ending in ":any") and params contain a URL, narrow the pattern
       to the observed domain.

Invariants:
    - Minimization is purely subtractive: steps are removed, params are
      dropped or narrowed, capabilities are restricted.
    - No new capabilities are introduced.
    - No new steps are added.
    - len(minimized) <= len(original) always.
    - Every transformation is recorded in ProgramDiff.

Usage::

    from program_layer.minimizer import Minimizer

    minimizer = Minimizer()
    minimized_steps, diff = minimizer.minimize(original_steps)
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse, urlunparse

from .review_models import (
    CapabilityChange,
    CandidateStep,
    ParamChange,
    ProgramDiff,
    RemovedStep,
)


class Minimizer:
    """
    Deterministic minimization engine.

    The minimizer is stateless — each call to minimize() is independent.
    """

    def minimize(
        self,
        steps: list[CandidateStep],
    ) -> tuple[list[CandidateStep], ProgramDiff]:
        """
        Apply all minimization rules to the given step list.

        Args:
            steps: the original candidate steps (not mutated).

        Returns:
            A (minimized_steps, diff) pair where:
                minimized_steps — the reduced step list (new objects)
                diff            — explicit record of every transformation

        Raises:
            TypeError: steps is not a list or contains non-CandidateStep items.
        """
        if not isinstance(steps, list):
            raise TypeError(
                f"Minimizer.minimize() expects a list of CandidateStep, "
                f"got {type(steps).__name__!r}"
            )
        for i, s in enumerate(steps):
            if not isinstance(s, CandidateStep):
                raise TypeError(
                    f"steps[{i}] must be a CandidateStep, "
                    f"got {type(s).__name__!r}"
                )

        # ----------------------------------------------------------------
        # Phase 1: Consecutive duplicate removal
        # ----------------------------------------------------------------
        deduped: list[CandidateStep] = []
        removed_steps: list[RemovedStep] = []
        # Maps index in deduped → original index (for diff step_index reporting)
        dedup_to_orig: dict[int, int] = {}

        prev_sig: str | None = None
        di = 0
        for orig_i, step in enumerate(steps):
            sig = _step_signature(step)
            if sig == prev_sig:
                removed_steps.append(
                    RemovedStep(
                        index=orig_i,
                        tool=step.tool,
                        reason=(
                            "consecutive duplicate: same tool and params "
                            "as the immediately preceding step"
                        ),
                    )
                )
            else:
                dedup_to_orig[di] = orig_i
                deduped.append(step)
                prev_sig = sig
                di += 1

        # ----------------------------------------------------------------
        # Phase 2: Parameter reduction
        # Phase 3: Capability surface reduction
        # ----------------------------------------------------------------
        param_changes: list[ParamChange] = []
        capability_reduction: list[CapabilityChange] = []
        minimized: list[CandidateStep] = []

        for di, step in enumerate(deduped):
            orig_idx = dedup_to_orig[di]

            # Reduce params
            reduced_params, step_param_changes = _reduce_params(
                step.params, orig_idx
            )

            # Reduce capabilities (uses reduced params for URL extraction)
            reduced_caps, step_cap_changes = _reduce_capabilities(
                step.capabilities_used, reduced_params, orig_idx
            )

            param_changes.extend(step_param_changes)
            capability_reduction.extend(step_cap_changes)

            minimized.append(
                CandidateStep(
                    tool=step.tool,
                    params=reduced_params,
                    provenance=step.provenance,
                    capabilities_used=reduced_caps,
                )
            )

        diff = ProgramDiff(
            removed_steps=tuple(removed_steps),
            param_changes=tuple(param_changes),
            capability_reduction=tuple(capability_reduction),
        )
        return minimized, diff


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _step_signature(step: CandidateStep) -> str:
    """
    Canonical string signature used for duplicate detection.

    Two steps are identical if they have the same tool and the same params
    after JSON-canonical serialization.  Provenance and capabilities_used
    are excluded — they are annotations, not execution-relevant inputs.
    """
    try:
        params_canonical = json.dumps(step.params, sort_keys=True, default=str)
    except Exception:
        params_canonical = repr(step.params)
    return f"{step.tool}:{params_canonical}"


def _reduce_params(
    params: dict[str, Any],
    step_index: int,
) -> tuple[dict[str, Any], list[ParamChange]]:
    """
    Apply parameter reduction rules to a single step's params dict.

    Rules:
        a. Remove keys whose value is None.
        b. Remove keys whose value is "" (empty string).
        c. For URL-type params (key contains "url", value is http/https URL),
           strip query string and fragment.

    Returns (reduced_params, list_of_ParamChange).
    """
    changes: list[ParamChange] = []
    result: dict[str, Any] = {}

    for key, value in params.items():
        # Rule a: drop None-valued params
        if value is None:
            changes.append(
                ParamChange(
                    step_index=step_index,
                    field=key,
                    before=value,
                    after=None,
                    reason="removed None-valued parameter",
                )
            )
            continue

        # Rule b: drop empty-string params
        if value == "":
            changes.append(
                ParamChange(
                    step_index=step_index,
                    field=key,
                    before=value,
                    after=None,
                    reason="removed empty-string parameter",
                )
            )
            continue

        # Rule c: strip query string from URL params
        if (
            isinstance(value, str)
            and "url" in key.lower()
            and _looks_like_url(value)
        ):
            stripped = _strip_query_and_fragment(value)
            if stripped != value:
                changes.append(
                    ParamChange(
                        step_index=step_index,
                        field=key,
                        before=value,
                        after=stripped,
                        reason="stripped query string and fragment from URL parameter",
                    )
                )
                result[key] = stripped
                continue

        result[key] = value

    return result, changes


def _reduce_capabilities(
    capabilities_used: tuple[str, ...] | None,
    params: dict[str, Any],
    step_index: int,
) -> tuple[tuple[str, ...] | None, list[CapabilityChange]]:
    """
    Apply capability surface reduction to a step's capabilities_used list.

    Rule: If a capability ends in ":any" (broad pattern) and the step's
    params contain a URL, replace ":any" with ":{domain}/*" scoped to the
    observed URL's domain.

    Only ":any" patterns are treated as broad.  All others are left as-is.

    Returns (reduced_capabilities, list_of_CapabilityChange).
    """
    if capabilities_used is None:
        return None, []

    domain = _extract_domain(params)
    changes: list[CapabilityChange] = []
    result: list[str] = []

    for cap in capabilities_used:
        if cap.endswith(":any") and domain is not None:
            tool_part = cap[: -len(":any")]
            narrowed = f"{tool_part}:{domain}/*"
            changes.append(
                CapabilityChange(
                    step_index=step_index,
                    before=cap,
                    after=narrowed,
                    reason=(
                        f"narrowed broad capability to observed URL domain "
                        f"({domain})"
                    ),
                )
            )
            result.append(narrowed)
        else:
            result.append(cap)

    return tuple(result), changes


def _looks_like_url(value: str) -> bool:
    """Return True if value is an HTTP or HTTPS URL."""
    return value.startswith(("http://", "https://"))


def _strip_query_and_fragment(url: str) -> str:
    """Remove query string and fragment from a URL, preserving scheme/host/path."""
    try:
        parsed = urlparse(url)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
        )
    except Exception:
        return url


def _extract_domain(params: dict[str, Any]) -> str | None:
    """
    Extract the domain from any URL-type parameter in params.

    Scans all keys whose name contains "url" and whose value is an HTTP/HTTPS
    URL.  Returns the first domain found, or None if none is present.
    """
    for key, value in params.items():
        if (
            isinstance(value, str)
            and "url" in key.lower()
            and _looks_like_url(value)
        ):
            try:
                parsed = urlparse(value)
                if parsed.netloc:
                    return parsed.netloc
            except Exception:
                pass
    return None
