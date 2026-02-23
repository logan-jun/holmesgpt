"""LangChain-based ReAct agent for HolmesGPT.

Lazy imports to avoid loading LangChain dependencies unless LANGCHAIN_AGENT=true.
"""


def get_agent_class():
    from holmes.core.langchain.agent import HolmesReActAgent

    return HolmesReActAgent


def get_investigator_class():
    from holmes.core.langchain.agent import LangChainIssueInvestigator

    return LangChainIssueInvestigator


__all__ = ["get_agent_class", "get_investigator_class"]
