"""
tests/economic/test_budget_enforcement.py — IRBuilder budget enforcement tests (v0.3-T2).

Invariants verified:
  - IRBuilder rejects IR construction when estimated cost exceeds budget limit
  - BudgetExceeded is a ConstructionError (IR never formed)
  - Budget check fires AFTER taint/capability/ontological checks
  - IRBuilder without economic_engine skips budget check (opt-in)
  - Budget check is skipped when cost_estimate is not provided
  - Successful build returns IR when within budget
  - EconomicPolicyEngine.record_actual_cost() accumulates session spend
  - Session spend reduces the effective per-request budget
"""

from __future__ import annotations

import pytest

from agent_hypervisor.economic.cost_estimator import CostEstimate
from agent_hypervisor.economic.economic_policy import CompiledBudget, EconomicPolicyEngine
from agent_hypervisor.economic.pricing_registry import ModelPricing, PricingRegistry
from agent_hypervisor.runtime.models import BudgetExceeded, ConstructionError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_registry(input_per_1k: float = 0.003, output_per_1k: float = 0.015) -> PricingRegistry:
    return PricingRegistry(
        model_pricing={
            "test-model": ModelPricing(
                model_name="test-model",
                input_per_1k=input_per_1k,
                output_per_1k=output_per_1k,
            )
        }
    )


def _make_engine(per_request: float, per_session: float = 999.0) -> EconomicPolicyEngine:
    budget = CompiledBudget(per_request=per_request, per_session=per_session)
    return EconomicPolicyEngine(budget=budget, pricing_registry=_make_registry())


def _make_estimate(total: float, model_name: str = "test-model") -> CostEstimate:
    return CostEstimate(
        model_name=model_name,
        input_tokens=100,
        output_tokens_cap=512,
        input_cost=0.0003,
        output_cost=total - 0.0003,
        tool_fixed_cost=0.0,
        uncertainty_mult=1.0,
        total=total,
        is_unbounded=False,
    )


# ── EconomicPolicyEngine.evaluate_budget() ────────────────────────────────────

class TestEvaluateBudget:
    def test_within_budget_returns_silently(self):
        engine = _make_engine(per_request=1.0)
        estimate = _make_estimate(0.50)
        engine.evaluate_budget(estimate)  # must not raise

    def test_exactly_at_limit_returns_silently(self):
        engine = _make_engine(per_request=0.50)
        estimate = _make_estimate(0.50)
        engine.evaluate_budget(estimate)  # must not raise

    def test_over_budget_raises_budget_exceeded(self):
        engine = _make_engine(per_request=0.50)
        estimate = _make_estimate(0.75)
        with pytest.raises(BudgetExceeded) as exc_info:
            engine.evaluate_budget(estimate)
        assert exc_info.value.estimated_cost == pytest.approx(0.75)
        assert exc_info.value.budget_limit == pytest.approx(0.50)

    def test_budget_exceeded_is_construction_error(self):
        engine = _make_engine(per_request=0.10)
        estimate = _make_estimate(0.50)
        with pytest.raises(ConstructionError):
            engine.evaluate_budget(estimate)

    def test_session_spend_reduces_effective_limit(self):
        engine = _make_engine(per_request=1.0, per_session=0.60)
        engine.record_actual_cost(0.50)  # session now has 0.10 remaining
        estimate = _make_estimate(0.20)
        with pytest.raises(BudgetExceeded) as exc_info:
            engine.evaluate_budget(estimate)
        # binding limit is min(per_request=1.0, remaining=0.10) = 0.10
        assert exc_info.value.budget_limit == pytest.approx(0.10)

    def test_per_request_override_applies(self):
        engine = _make_engine(per_request=1.0)
        estimate = _make_estimate(0.30)
        with pytest.raises(BudgetExceeded):
            engine.evaluate_budget(estimate, request_budget_override=0.20)

    def test_replan_hint_present_when_cheaper_model_exists(self):
        registry = PricingRegistry(
            model_pricing={
                "expensive-model": ModelPricing("expensive-model", 0.030, 0.060),
                "cheap-model":     ModelPricing("cheap-model",     0.003, 0.006),
            }
        )
        budget = CompiledBudget(per_request=0.01, per_session=999.0)
        engine = EconomicPolicyEngine(budget=budget, pricing_registry=registry)
        estimate = CostEstimate(
            model_name="expensive-model",
            input_tokens=100,
            output_tokens_cap=512,
            input_cost=0.003,
            output_cost=0.03072,
            tool_fixed_cost=0.0,
            uncertainty_mult=1.0,
            total=0.03372,
            is_unbounded=False,
        )
        with pytest.raises(BudgetExceeded) as exc_info:
            engine.evaluate_budget(estimate)
        hint = exc_info.value.replan_hint
        assert hint is not None
        assert hint.switch_model == "cheap-model"


# ── IRBuilder budget enforcement ──────────────────────────────────────────────

class TestIRBuilderBudget:
    """IRBuilder budget enforcement: checked at construction, not execution."""

    def _build_policy(self):
        from agent_hypervisor.runtime.compile import compile_world
        import tempfile, os, yaml

        manifest = {
            "metadata": {"workflow_id": "test"},
            "actions": {
                "read_data": {"type": "internal", "approval_required": False},
            },
            "capabilities": {"trusted": ["internal"]},
            "taint_rules": [],
            "trust": {"user": "trusted"},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as fh:
            yaml.dump(manifest, fh)
            tmp = fh.name

        try:
            return compile_world(tmp)
        finally:
            os.unlink(tmp)

    def _build_runtime(self, economic_engine=None):
        from agent_hypervisor.runtime.ir import IRBuilder
        policy = self._build_policy()
        return IRBuilder(policy, economic_engine=economic_engine)

    def _make_source(self, builder):
        from agent_hypervisor.runtime.channel import Channel
        policy = self._build_policy()
        channel = Channel(identity="user", policy=policy)
        return channel.source

    def _clean_taint(self):
        from agent_hypervisor.runtime.taint import TaintContext
        return TaintContext.clean()

    def test_budget_exceeded_blocks_ir_construction(self):
        engine = _make_engine(per_request=0.001)
        builder = self._build_runtime(economic_engine=engine)
        source = self._make_source(builder)
        estimate = _make_estimate(total=1.00)
        with pytest.raises(BudgetExceeded):
            builder.build("read_data", source, {}, self._clean_taint(), cost_estimate=estimate)

    def test_within_budget_builds_ir(self):
        from agent_hypervisor.runtime.ir import IntentIR
        engine = _make_engine(per_request=10.0)
        builder = self._build_runtime(economic_engine=engine)
        source = self._make_source(builder)
        estimate = _make_estimate(total=0.01)
        ir = builder.build("read_data", source, {}, self._clean_taint(), cost_estimate=estimate)
        assert isinstance(ir, IntentIR)

    def test_no_engine_skips_budget_check(self):
        """Without an economic engine, any estimate is ignored."""
        from agent_hypervisor.runtime.ir import IntentIR
        builder = self._build_runtime(economic_engine=None)
        source = self._make_source(builder)
        estimate = _make_estimate(total=999999.0)  # absurdly large
        ir = builder.build("read_data", source, {}, self._clean_taint(), cost_estimate=estimate)
        assert isinstance(ir, IntentIR)

    def test_no_estimate_skips_budget_check(self):
        """With an engine but no estimate, budget check is skipped."""
        from agent_hypervisor.runtime.ir import IntentIR
        engine = _make_engine(per_request=0.001)
        builder = self._build_runtime(economic_engine=engine)
        source = self._make_source(builder)
        # No cost_estimate → check skipped → IR built successfully
        ir = builder.build("read_data", source, {}, self._clean_taint())
        assert isinstance(ir, IntentIR)

    def test_budget_check_fires_after_ontological_check(self):
        """Ontological check (unknown action) fires before budget check."""
        engine = _make_engine(per_request=0.001)
        builder = self._build_runtime(economic_engine=engine)
        source = self._make_source(builder)
        estimate = _make_estimate(total=999.0)
        from agent_hypervisor.runtime.models import NonExistentAction
        with pytest.raises(NonExistentAction):
            builder.build("nonexistent_action", source, {}, self._clean_taint(), cost_estimate=estimate)


# ── ahc cost-profile CLI ──────────────────────────────────────────────────────

class TestCostProfileCLI:
    def test_cost_profile_prints_percentile_table(self, tmp_path):
        import json
        from click.testing import CliRunner
        from agent_hypervisor.compiler.cli import cli

        trace = tmp_path / "trace.jsonl"
        observations = [
            {"action_name": "summarize", "model_name": "gpt-4", "actual_cost": 0.01},
            {"action_name": "summarize", "model_name": "gpt-4", "actual_cost": 0.02},
            {"action_name": "summarize", "model_name": "gpt-4", "actual_cost": 0.03},
            {"action_name": "read_data", "model_name": "gpt-4", "actual_cost": 0.005},
        ]
        trace.write_text("\n".join(json.dumps(o) for o in observations))

        runner = CliRunner()
        result = runner.invoke(cli, ["cost-profile", str(trace)])
        assert result.exit_code == 0, result.output
        assert "summarize" in result.output
        assert "read_data" in result.output
        assert "p50" in result.output

    def test_cost_profile_empty_file_exits_nonzero(self, tmp_path):
        from click.testing import CliRunner
        from agent_hypervisor.compiler.cli import cli

        trace = tmp_path / "empty.jsonl"
        trace.write_text("")

        runner = CliRunner()
        result = runner.invoke(cli, ["cost-profile", str(trace)])
        assert result.exit_code != 0
