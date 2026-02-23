"""LangChain callbacks for cost tracking and streaming event conversion."""

import logging
from typing import Any, Dict, List, Optional, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult as LCLLMResult

cost_logger = logging.getLogger("holmes.costs")


class HolmesCostTracker(BaseCallbackHandler):
    """Tracks cost and token usage across LLM calls in a LangGraph session."""

    def __init__(self):
        self.total_cost: float = 0.0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.llm_call_count: int = 0

    def on_llm_end(self, response: LCLLMResult, **kwargs: Any) -> None:
        """Extract cost info from LLM response."""
        self.llm_call_count += 1

        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if usage:
                self.prompt_tokens += usage.get("prompt_tokens", 0)
                self.completion_tokens += usage.get("completion_tokens", 0)
                self.total_tokens += usage.get("total_tokens", 0)

            cost = response.llm_output.get("response_cost", 0)
            if cost:
                self.total_cost += float(cost)

        cost_logger.debug(
            f"LLM call #{self.llm_call_count} | "
            f"Cost: ${self.total_cost:.6f} | "
            f"Tokens: {self.prompt_tokens} prompt + {self.completion_tokens} completion"
        )

    def get_costs_dict(self) -> Dict[str, Any]:
        """Return cost info as a dict compatible with LLMResult fields."""
        return {
            "total_cost": self.total_cost,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    def reset(self) -> None:
        """Reset cost tracker for a new interaction."""
        self.total_cost = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.llm_call_count = 0
