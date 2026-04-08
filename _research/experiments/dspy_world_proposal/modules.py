"""
modules.py — DSPy modules / pipelines for the World Proposal experiment.

Track A: ThreatAndMinimizationPipeline
  Stages: ExtractCapabilities → EnumerateAttacks → MinimizeCapabilities
          → SuggestSurrogates → BuildDraftManifest

Track B: CalibrationReviewPipeline
  Single-step: ReviewCapabilityRequest → CalibrationVerdict
"""

from __future__ import annotations

import json

import dspy

from signatures import (
    BuildDraftManifest,
    EnumerateAttacks,
    ExtractCapabilities,
    MinimizeCapabilities,
    ReviewCapabilityRequest,
    SuggestSurrogates,
)


class ThreatAndMinimizationPipeline(dspy.Module):
    """
    Track A: Workflow threat analysis and capability minimization.

    Runs five sequential DSPy predictors. Each stage passes structured JSON
    to the next so context is explicit rather than implicit in the LM.

    Returns a plain dict so callers don't need to import Pydantic models.
    """

    def __init__(self) -> None:
        self.extract = dspy.Predict(ExtractCapabilities)
        self.attack = dspy.Predict(EnumerateAttacks)
        self.minimize = dspy.Predict(MinimizeCapabilities)
        self.surrogates = dspy.Predict(SuggestSurrogates)
        self.manifest = dspy.Predict(BuildDraftManifest)

    def forward(self, workflow_description: str, tool_list: str = "none") -> dict:
        # --- Stage 1: infer capability set ---
        cap_result = self.extract(
            workflow_description=workflow_description,
            tool_list=tool_list,
        )
        capabilities = cap_result.capabilities
        caps_json = json.dumps([c.model_dump() for c in capabilities], indent=2)

        # --- Stage 2: enumerate attack scenarios ---
        atk_result = self.attack(
            workflow_description=workflow_description,
            capabilities_json=caps_json,
        )
        attacks = atk_result.attack_scenarios
        attacks_json = json.dumps([a.model_dump() for a in attacks], indent=2)

        # --- Stage 3: minimize capability set ---
        min_result = self.minimize(
            workflow_description=workflow_description,
            capabilities_json=caps_json,
            attacks_json=attacks_json,
        )
        minimized = min_result.minimized_capabilities
        removed = min_result.removed_capabilities
        min_json = json.dumps([c.model_dump() for c in minimized], indent=2)
        removed_json = json.dumps(removed, indent=2)

        # --- Stage 4: propose surrogates ---
        sur_result = self.surrogates(
            workflow_description=workflow_description,
            minimized_capabilities_json=min_json,
        )
        surrogates_list = sur_result.surrogate_mappings
        surrogates_json = json.dumps(
            [s.model_dump() for s in surrogates_list], indent=2
        )

        # --- Stage 5: build draft manifest ---
        mfst_result = self.manifest(
            workflow_description=workflow_description,
            minimized_capabilities_json=min_json,
            surrogates_json=surrogates_json,
            removed_capabilities_json=removed_json,
        )

        return {
            "track": "A",
            "workflow": workflow_description,
            "inferred_capabilities": [c.model_dump() for c in capabilities],
            "attack_scenarios": [a.model_dump() for a in attacks],
            "minimized_capabilities": [c.model_dump() for c in minimized],
            "removed_capabilities": removed,
            "surrogate_suggestions": [s.model_dump() for s in surrogates_list],
            "draft_manifest": mfst_result.draft_manifest.model_dump(),
        }


class CalibrationReviewPipeline(dspy.Module):
    """
    Track B: Single-capability calibration review.

    Evaluates whether a capability request is directly implied, derived,
    or adversarially induced. Produces a structured CalibrationVerdict.
    """

    def __init__(self) -> None:
        self.review = dspy.Predict(ReviewCapabilityRequest)

    def forward(
        self,
        capability_request: str,
        workflow_goal: str,
        provenance: str,
    ) -> dict:
        result = self.review(
            capability_request=capability_request,
            workflow_goal=workflow_goal,
            provenance=provenance,
        )
        return {
            "track": "B",
            "capability_request": capability_request,
            "workflow_goal": workflow_goal,
            "provenance": provenance,
            "verdict": result.verdict.model_dump(),
        }
