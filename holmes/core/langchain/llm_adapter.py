import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_litellm import ChatLiteLLM

from holmes.common.env_vars import LLM_REQUEST_TIMEOUT, TEMPERATURE
from holmes.core.llm import DefaultLLM, LLM

logger = logging.getLogger(__name__)


class HolmesChatModelFactory:
    """Factory for creating a LangChain ChatModel from Holmes DefaultLLM config."""

    @staticmethod
    def create(llm: LLM) -> BaseChatModel:
        """Create a ChatLiteLLM instance with identical config to DefaultLLM.

        This bridges Holmes' LLM configuration into LangChain's ecosystem,
        ensuring the same model, credentials, and parameters are used.
        """
        if not isinstance(llm, DefaultLLM):
            raise TypeError(f"Expected DefaultLLM, got {type(llm).__name__}")

        model_name = llm.model
        if llm.is_robusta_model:
            model_name = llm.get_litellm_corrected_name_for_robusta_ai()

        kwargs: dict = {
            "model": model_name,
            "temperature": TEMPERATURE,
            "timeout": LLM_REQUEST_TIMEOUT,
        }

        if llm.api_key:
            kwargs["api_key"] = llm.api_key
        if llm.api_base:
            kwargs["api_base"] = llm.api_base
        if llm.api_version:
            kwargs["api_version"] = llm.api_version

        # Pass through extra LLM args (thinking, extra_headers, etc.)
        extra_args = {k: v for k, v in llm.args.items() if k != "custom_args"}
        kwargs.update(extra_args)

        logger.info(f"Creating ChatLiteLLM with model={model_name}")
        return ChatLiteLLM(**kwargs)
