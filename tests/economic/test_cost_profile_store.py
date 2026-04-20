"""
tests/economic/test_cost_profile_store.py — CostProfileStore.percentile() tests.

Coverage:
    1.  Empty collection raises KeyError
    2.  Single observation returns that value for any valid p
    3.  p=0 returns minimum
    4.  p=100 returns maximum
    5.  p=50 interpolates correctly for even-count list
    6.  p=50 returns middle value for odd-count list
    7.  p=90 for known dataset matches expected interpolated value
    8.  p=99 for known dataset matches expected interpolated value
    9.  Linear interpolation is exact at integer index positions
    10. p < 0 raises ValueError
    11. p > 100 raises ValueError
    12. Queries are scoped to (action_name, model_name) — no cross-contamination
    13. model_name="" is a valid key distinct from named models
    14. Large dataset percentiles are stable (no off-by-one)
"""

from __future__ import annotations

import math

import pytest

from agent_hypervisor.economic.cost_profile_store import CostObservation, CostProfileStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obs(action: str, cost: float, model: str = "gpt-4o") -> CostObservation:
    return CostObservation(action_name=action, actual_cost=cost, model_name=model)


def _store_with(*costs: float, action: str = "send_email", model: str = "gpt-4o") -> CostProfileStore:
    store = CostProfileStore()
    for c in costs:
        store.record(_obs(action=action, cost=c, model=model))
    return store


# ---------------------------------------------------------------------------
# Edge cases: empty and single-element
# ---------------------------------------------------------------------------


class TestPercentileEmpty:
    def test_empty_store_raises_key_error(self):
        store = CostProfileStore()
        with pytest.raises(KeyError, match="send_email"):
            store.percentile("send_email", "gpt-4o", 50)

    def test_empty_for_specific_pair_raises_even_if_other_pairs_exist(self):
        store = _store_with(1.0, action="send_email", model="gpt-4o")
        with pytest.raises(KeyError):
            store.percentile("send_email", "other-model", 50)

    def test_wrong_action_raises_key_error(self):
        store = _store_with(1.0, action="send_email", model="gpt-4o")
        with pytest.raises(KeyError):
            store.percentile("fetch_document", "gpt-4o", 50)


class TestPercentileSingleObservation:
    def test_single_p0_returns_value(self):
        store = _store_with(0.42)
        assert store.percentile("send_email", "gpt-4o", 0) == pytest.approx(0.42)

    def test_single_p50_returns_value(self):
        store = _store_with(0.42)
        assert store.percentile("send_email", "gpt-4o", 50) == pytest.approx(0.42)

    def test_single_p100_returns_value(self):
        store = _store_with(0.42)
        assert store.percentile("send_email", "gpt-4o", 100) == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Boundary percentiles
# ---------------------------------------------------------------------------


class TestPercentileBounds:
    def test_p0_returns_minimum(self):
        store = _store_with(5.0, 1.0, 3.0, 2.0, 4.0)
        assert store.percentile("send_email", "gpt-4o", 0) == pytest.approx(1.0)

    def test_p100_returns_maximum(self):
        store = _store_with(5.0, 1.0, 3.0, 2.0, 4.0)
        assert store.percentile("send_email", "gpt-4o", 100) == pytest.approx(5.0)

    def test_p_below_0_raises_value_error(self):
        store = _store_with(1.0, 2.0)
        with pytest.raises(ValueError, match="\\[0, 100\\]"):
            store.percentile("send_email", "gpt-4o", -1)

    def test_p_above_100_raises_value_error(self):
        store = _store_with(1.0, 2.0)
        with pytest.raises(ValueError, match="\\[0, 100\\]"):
            store.percentile("send_email", "gpt-4o", 101)

    def test_p_exactly_0_is_valid(self):
        store = _store_with(10.0, 20.0)
        assert store.percentile("send_email", "gpt-4o", 0.0) == pytest.approx(10.0)

    def test_p_exactly_100_is_valid(self):
        store = _store_with(10.0, 20.0)
        assert store.percentile("send_email", "gpt-4o", 100.0) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Interpolation correctness
# ---------------------------------------------------------------------------


class TestPercentileInterpolation:
    def test_p50_two_values(self):
        # [10, 20]: index = 0.5 × 1 = 0.5 → 10 + 0.5 × (20 - 10) = 15
        store = _store_with(10.0, 20.0)
        assert store.percentile("send_email", "gpt-4o", 50) == pytest.approx(15.0)

    def test_p50_odd_count_returns_middle(self):
        # [1, 2, 3, 4, 5]: p50 index = 0.5 × 4 = 2 → values[2] = 3
        store = _store_with(3.0, 1.0, 5.0, 2.0, 4.0)
        assert store.percentile("send_email", "gpt-4o", 50) == pytest.approx(3.0)

    def test_p25_four_values(self):
        # [10, 20, 30, 40]: p25 index = 0.25 × 3 = 0.75 → 10 + 0.75 × 10 = 17.5
        store = _store_with(10.0, 20.0, 30.0, 40.0)
        assert store.percentile("send_email", "gpt-4o", 25) == pytest.approx(17.5)

    def test_p75_four_values(self):
        # [10, 20, 30, 40]: p75 index = 0.75 × 3 = 2.25 → 30 + 0.25 × 10 = 32.5
        store = _store_with(10.0, 20.0, 30.0, 40.0)
        assert store.percentile("send_email", "gpt-4o", 75) == pytest.approx(32.5)

    def test_p90_ten_values(self):
        # [1..10]: p90 index = 0.9 × 9 = 8.1 → 9 + 0.1 × (10 - 9) = 9.1
        store = _store_with(*[float(i) for i in range(1, 11)])
        assert store.percentile("send_email", "gpt-4o", 90) == pytest.approx(9.1)

    def test_p99_ten_values(self):
        # [1..10]: p99 index = 0.99 × 9 = 8.91 → 9 + 0.91 × (10 - 9) = 9.91
        store = _store_with(*[float(i) for i in range(1, 11)])
        assert store.percentile("send_email", "gpt-4o", 99) == pytest.approx(9.91)

    def test_integer_index_returns_exact_value(self):
        # [0, 1, 2, 3, 4]: p50 index = 2 exactly → values[2] = 2.0
        store = _store_with(0.0, 1.0, 2.0, 3.0, 4.0)
        result = store.percentile("send_email", "gpt-4o", 50)
        assert result == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Scoping: queries must not cross (action, model) boundaries
# ---------------------------------------------------------------------------


class TestPercentileScoping:
    def test_different_actions_are_independent(self):
        store = CostProfileStore()
        store.record(_obs("action_a", 1.0, "gpt-4o"))
        store.record(_obs("action_a", 2.0, "gpt-4o"))
        store.record(_obs("action_b", 100.0, "gpt-4o"))
        store.record(_obs("action_b", 200.0, "gpt-4o"))

        assert store.percentile("action_a", "gpt-4o", 100) == pytest.approx(2.0)
        assert store.percentile("action_b", "gpt-4o", 0) == pytest.approx(100.0)

    def test_different_models_are_independent(self):
        store = CostProfileStore()
        store.record(_obs("send_email", 0.01, "gpt-4o-mini"))
        store.record(_obs("send_email", 0.02, "gpt-4o-mini"))
        store.record(_obs("send_email", 1.00, "gpt-4o"))
        store.record(_obs("send_email", 2.00, "gpt-4o"))

        assert store.percentile("send_email", "gpt-4o-mini", 100) == pytest.approx(0.02)
        assert store.percentile("send_email", "gpt-4o", 0) == pytest.approx(1.00)

    def test_empty_model_name_is_valid_key(self):
        store = CostProfileStore()
        store.record(_obs("count_words", 0.5, model=""))
        store.record(_obs("count_words", 1.5, model=""))

        assert store.percentile("count_words", "", 50) == pytest.approx(1.0)

    def test_observations_are_insertion_order_independent(self):
        # Results must depend only on sorted values, not insertion order
        store_asc = _store_with(1.0, 2.0, 3.0, 4.0, 5.0)
        store_desc = _store_with(5.0, 4.0, 3.0, 2.0, 1.0)
        store_random = _store_with(3.0, 1.0, 5.0, 2.0, 4.0)

        for store in (store_asc, store_desc, store_random):
            assert store.percentile("send_email", "gpt-4o", 50) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Large dataset stability
# ---------------------------------------------------------------------------


class TestPercentileLargeDataset:
    def test_100_uniform_values_p50_is_median(self):
        store = _store_with(*[float(i) for i in range(1, 101)])
        # [1..100]: p50 index = 0.5 × 99 = 49.5 → 50 + 0.5 × (51 - 50) = 50.5
        result = store.percentile("send_email", "gpt-4o", 50)
        assert result == pytest.approx(50.5)

    def test_100_uniform_values_p99_near_max(self):
        store = _store_with(*[float(i) for i in range(1, 101)])
        result = store.percentile("send_email", "gpt-4o", 99)
        # p99 index = 0.99 × 99 = 98.01 → 99 + 0.01 × (100 - 99) = 99.01
        assert result == pytest.approx(99.01)

    def test_result_is_always_within_observed_range(self):
        import random
        random.seed(42)
        costs = [random.uniform(0.0, 10.0) for _ in range(200)]
        store = _store_with(*costs)
        for p in (0, 10, 25, 50, 75, 90, 99, 100):
            result = store.percentile("send_email", "gpt-4o", p)
            assert min(costs) <= result <= max(costs), (
                f"p={p} result {result} is outside [{min(costs)}, {max(costs)}]"
            )
