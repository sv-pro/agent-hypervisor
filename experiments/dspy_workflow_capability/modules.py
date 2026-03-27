"""
modules.py — DSPy module skeletons for workflow capability analysis.

Phase 1: Wiring only. No prompt engineering, no optimization, no heavy logic.

Two top-level modules:

    WorkflowSecurityAnalyzer
        Runs the full pipeline: extract → attack → minimize → surrogate → manifest
        Input:  workflow_description (str)
        Output: AnalysisResult (dataclass)

    CapabilityReviewer
        Runs the calibration review flow for a single capability request.
        Input:  workflow_description, requested_capability, request_context
        Output: ReviewResult (dataclass)

Both modules are dspy.Module subclasses.
forward() is skeletal — it calls predictors in order and returns a result.
No error handling, no fallbacks, no retries in this phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import dspy

from .signatures import (
    BuildDraftManifest,
    EnumerateAttacks,
    ExtractCapabilities,
    MinimizeCapabilities,
    ReviewCapabilityRequest,
    SuggestSurrogates,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Structured output of WorkflowSecurityAnalyzer."""

    capabilities: list[str] = field(default_factory=list)
    attacks: list[dict] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)
    surrogates: dict[str, dict] = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)


@dataclass
class ReviewResult:
    """Structured output of CapabilityReviewer."""

    decision: str = ""
    implied_by_workflow: bool = False
    adversarial_risk: str = "none"
    rationale: str = ""
    reviewer_action: str = ""


# ---------------------------------------------------------------------------
# WorkflowSecurityAnalyzer
# ---------------------------------------------------------------------------

class WorkflowSecurityAnalyzer(dspy.Module):
    """
    Full pipeline: given a workflow description, produce a draft manifest
    with attack analysis and minimized, surrogate-substituted capabilities.

    Pipeline:
        ExtractCapabilities
            → EnumerateAttacks
            → MinimizeCapabilities
            → SuggestSurrogates
            → BuildDraftManifest

    Each step is a dspy.Predict over its corresponding signature.
    No step modifies the workflow_description — it flows unchanged.
    """

    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.Predict(ExtractCapabilities)
        self.attack = dspy.Predict(EnumerateAttacks)
        self.minimize = dspy.Predict(MinimizeCapabilities)
        self.surrogate = dspy.Predict(SuggestSurrogates)
        self.manifest = dspy.Predict(BuildDraftManifest)

    def forward(self, workflow_description: str) -> AnalysisResult:
        extracted = self.extract(workflow_description=workflow_description)

        attacked = self.attack(
            workflow_description=workflow_description,
            capabilities=extracted.capabilities,
        )

        minimized = self.minimize(
            workflow_description=workflow_description,
            capabilities=extracted.capabilities,
            attacks=attacked.attacks,
        )

        surrogated = self.surrogate(
            workflow_description=workflow_description,
            kept_capabilities=minimized.kept,
        )

        drafted = self.manifest(
            workflow_description=workflow_description,
            kept_capabilities=minimized.kept,
            surrogates=surrogated.surrogates,
        )

        return AnalysisResult(
            capabilities=extracted.capabilities,
            attacks=attacked.attacks,
            kept=minimized.kept,
            dropped=minimized.dropped,
            surrogates=surrogated.surrogates,
            manifest=drafted.manifest,
        )


# ---------------------------------------------------------------------------
# CapabilityReviewer
# ---------------------------------------------------------------------------

class CapabilityReviewer(dspy.Module):
    """
    Calibration review: given a capability request and the workflow it claims
    to support, decide allow / flag / deny.

    Single-step module. The review is one dspy.Predict call.
    No chaining — this is intentionally atomic.
    """

    def __init__(self) -> None:
        super().__init__()
        self.review = dspy.Predict(ReviewCapabilityRequest)

    def forward(
        self,
        workflow_description: str,
        requested_capability: str,
        request_context: str,
    ) -> ReviewResult:
        result = self.review(
            workflow_description=workflow_description,
            requested_capability=requested_capability,
            request_context=request_context,
        )

        return ReviewResult(
            decision=result.decision,
            implied_by_workflow=result.implied_by_workflow,
            adversarial_risk=result.adversarial_risk,
            rationale=result.rationale,
            reviewer_action=result.reviewer_action,
        )
