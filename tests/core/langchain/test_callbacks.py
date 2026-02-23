"""Tests for HolmesCostTracker callback."""

import pytest

from holmes.core.langchain.callbacks import HolmesCostTracker


class TestHolmesCostTracker:
    def test_initial_state(self):
        tracker = HolmesCostTracker()
        assert tracker.total_cost == 0.0
        assert tracker.prompt_tokens == 0
        assert tracker.completion_tokens == 0
        assert tracker.total_tokens == 0
        assert tracker.llm_call_count == 0

    def test_get_costs_dict(self):
        tracker = HolmesCostTracker()
        costs = tracker.get_costs_dict()
        assert costs == {
            "total_cost": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def test_reset(self):
        tracker = HolmesCostTracker()
        tracker.total_cost = 1.0
        tracker.prompt_tokens = 100
        tracker.llm_call_count = 3
        tracker.reset()
        assert tracker.total_cost == 0.0
        assert tracker.prompt_tokens == 0
        assert tracker.llm_call_count == 0
