"""Tests for OpenAI ↔ LangChain message conversion."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from holmes.core.langchain.message_converter import langchain_to_openai, openai_to_langchain


class TestOpenAIToLangChain:
    def test_system_message(self):
        msgs = [{"role": "system", "content": "You are helpful"}]
        result = openai_to_langchain(msgs)
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are helpful"

    def test_user_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = openai_to_langchain(msgs)
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello"

    def test_assistant_message_text_only(self):
        msgs = [{"role": "assistant", "content": "Hi there"}]
        result = openai_to_langchain(msgs)
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert result[0].content == "Hi there"
        assert result[0].tool_calls == []

    def test_assistant_message_with_tool_calls(self):
        msgs = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "get_pods",
                            "arguments": '{"namespace": "default"}',
                        },
                    }
                ],
            }
        ]
        result = openai_to_langchain(msgs)
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0]["name"] == "get_pods"
        assert result[0].tool_calls[0]["args"] == {"namespace": "default"}
        assert result[0].tool_calls[0]["id"] == "tc_1"

    def test_tool_message(self):
        msgs = [
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "pod list here",
            }
        ]
        result = openai_to_langchain(msgs)
        assert len(result) == 1
        assert isinstance(result[0], ToolMessage)
        assert result[0].content == "pod list here"
        assert result[0].tool_call_id == "tc_1"

    def test_full_conversation(self):
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "List pods"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "kubectl_get", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": "pod-1\npod-2"},
            {"role": "assistant", "content": "Found 2 pods"},
        ]
        result = openai_to_langchain(msgs)
        assert len(result) == 5
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)
        assert isinstance(result[3], ToolMessage)
        assert isinstance(result[4], AIMessage)

    def test_empty_messages(self):
        result = openai_to_langchain([])
        assert result == []

    def test_assistant_with_none_content(self):
        msgs = [{"role": "assistant", "content": None}]
        result = openai_to_langchain(msgs)
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert result[0].content == ""


class TestLangChainToOpenAI:
    def test_system_message(self):
        msgs = [SystemMessage(content="System")]
        result = langchain_to_openai(msgs)
        assert result == [{"role": "system", "content": "System"}]

    def test_human_message(self):
        msgs = [HumanMessage(content="Hello")]
        result = langchain_to_openai(msgs)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_ai_message_text(self):
        msgs = [AIMessage(content="Response")]
        result = langchain_to_openai(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Response"

    def test_ai_message_with_tool_calls(self):
        msgs = [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_pods", "args": {"ns": "default"}, "id": "tc_1"}
                ],
            )
        ]
        result = langchain_to_openai(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "tc_1"
        assert tc["function"]["name"] == "get_pods"

    def test_tool_message(self):
        msgs = [ToolMessage(content="result", tool_call_id="tc_1")]
        result = langchain_to_openai(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tc_1"
        assert result[0]["content"] == "result"


class TestRoundTrip:
    def test_roundtrip_preserves_structure(self):
        original = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What pods?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "kubectl_get",
                            "arguments": '{"resource": "pods"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": "pod-1"},
            {"role": "assistant", "content": "Found pod-1"},
        ]

        lc_msgs = openai_to_langchain(original)
        roundtripped = langchain_to_openai(lc_msgs)

        assert len(roundtripped) == len(original)
        assert roundtripped[0]["role"] == "system"
        assert roundtripped[1]["role"] == "user"
        assert roundtripped[2]["role"] == "assistant"
        assert roundtripped[3]["role"] == "tool"
        assert roundtripped[4]["role"] == "assistant"
        assert roundtripped[4]["content"] == "Found pod-1"
