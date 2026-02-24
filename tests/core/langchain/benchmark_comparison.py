"""Benchmark: Original ToolCallingLLM vs LangChain ReAct Agent

Compares:
1. Tool call consistency (same tools called across runs)
2. Total response time
3. Answer quality (length, structure, key content)
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

os.environ["TEMPERATURE"] = "0"
os.environ["OPENROUTER_API_KEY"] = sys.argv[1] if len(sys.argv) > 1 else ""

import logging

logging.basicConfig(level=logging.WARNING)

import holmes.config as holmes_config
from holmes.config import Config


MODEL = "openrouter/openai/gpt-oss-120b"
API_KEY = os.environ["OPENROUTER_API_KEY"]
RUNS_PER_QUESTION = 3

QUESTIONS = [
    {
        "id": "Q1_simple",
        "name": "Simple: Pod 목록 조회",
        "system": "You are a Kubernetes assistant.",
        "user": "What pods are in test-app namespace? Tell me their names and status.",
        "expected_keywords": ["nginx-web", "crashloop-app"],
    },
    {
        "id": "Q2_diagnosis",
        "name": "Medium: CrashLoop 진단",
        "system": "You are a Kubernetes troubleshooting assistant.",
        "user": "There is a crashing pod in test-app namespace. Find out what pod it is and why it crashes.",
        "expected_keywords": ["crashloop-app", "exit", "CrashLoopBackOff"],
    },
    {
        "id": "Q3_multi",
        "name": "Complex: 전체 네임스페이스 분석",
        "system": "You are a Kubernetes troubleshooting assistant.",
        "user": "Analyze the test-app namespace. List all resources (pods, services, deployments) and report any issues you find.",
        "expected_keywords": ["nginx-web", "crashloop-app", "service", "deployment"],
    },
]


@dataclass
class RunResult:
    question_id: str
    agent_type: str
    run_number: int
    elapsed_seconds: float
    tool_names: List[str]
    tool_count: int
    llm_calls: int
    answer_length: int
    answer_text: str
    keywords_found: List[str]
    keywords_missing: List[str]


def create_agent(use_langchain: bool):
    # Toggle feature flag at module level
    holmes_config.LANGCHAIN_AGENT = use_langchain
    config = Config(model=MODEL, api_key=API_KEY)
    return config.create_console_toolcalling_llm()


def run_single(agent, question: dict, agent_type: str, run_number: int) -> RunResult:
    start = time.time()
    result = agent.prompt_call(
        system_prompt=question["system"],
        user_prompt=question["user"],
    )
    elapsed = time.time() - start

    tool_names = [tc.tool_name for tc in result.tool_calls]
    answer = result.result or ""

    keywords_found = [kw for kw in question["expected_keywords"] if kw.lower() in answer.lower()]
    keywords_missing = [kw for kw in question["expected_keywords"] if kw.lower() not in answer.lower()]

    return RunResult(
        question_id=question["id"],
        agent_type=agent_type,
        run_number=run_number,
        elapsed_seconds=elapsed,
        tool_names=tool_names,
        tool_count=len(tool_names),
        llm_calls=result.num_llm_calls,
        answer_length=len(answer),
        answer_text=answer,
        keywords_found=keywords_found,
        keywords_missing=keywords_missing,
    )


def tool_consistency(results: List[RunResult]) -> float:
    """Calculate tool call consistency (0.0~1.0) across runs."""
    if len(results) <= 1:
        return 1.0
    tool_sets = [set(r.tool_names) for r in results]
    # Jaccard similarity between all pairs
    pairs = 0
    total_sim = 0.0
    for i in range(len(tool_sets)):
        for j in range(i + 1, len(tool_sets)):
            union = tool_sets[i] | tool_sets[j]
            if not union:
                total_sim += 1.0
            else:
                total_sim += len(tool_sets[i] & tool_sets[j]) / len(union)
            pairs += 1
    return total_sim / pairs if pairs > 0 else 1.0


def print_separator(char="=", width=80):
    print(char * width)


def print_header(text: str):
    print_separator()
    print(f"  {text}")
    print_separator()


def main():
    if not API_KEY:
        print("Usage: python benchmark_comparison.py <OPENROUTER_API_KEY>")
        sys.exit(1)

    all_results: List[RunResult] = []

    for q in QUESTIONS:
        print_header(f"{q['name']}")
        print(f"  Q: {q['user']}")
        print()

        for agent_label, use_lc in [("Original", False), ("LangChain", True)]:
            agent = create_agent(use_lc)
            q_results = []

            for run in range(1, RUNS_PER_QUESTION + 1):
                print(f"  [{agent_label}] Run {run}/{RUNS_PER_QUESTION}...", end="", flush=True)
                r = run_single(agent, q, agent_label, run)
                q_results.append(r)
                all_results.append(r)
                print(
                    f" {r.elapsed_seconds:.1f}s | "
                    f"{r.tool_count} tools | "
                    f"{r.llm_calls} LLM calls | "
                    f"{r.answer_length} chars | "
                    f"keywords {len(r.keywords_found)}/{len(q['expected_keywords'])}"
                )

            # Per-agent summary for this question
            avg_time = sum(r.elapsed_seconds for r in q_results) / len(q_results)
            consistency = tool_consistency(q_results)
            avg_keywords = sum(len(r.keywords_found) for r in q_results) / len(q_results)
            total_kw = len(q["expected_keywords"])
            print(
                f"  [{agent_label}] AVG: {avg_time:.1f}s | "
                f"consistency: {consistency:.0%} | "
                f"keywords: {avg_keywords:.1f}/{total_kw}"
            )
            print()

    # Final comparison table
    print()
    print_header("FINAL COMPARISON")
    print()

    for agent_label in ["Original", "LangChain"]:
        agent_results = [r for r in all_results if r.agent_type == agent_label]
        print(f"  === {agent_label} Agent ===")

        total_time = sum(r.elapsed_seconds for r in agent_results)
        avg_time = total_time / len(agent_results)
        total_tools = sum(r.tool_count for r in agent_results)
        total_llm = sum(r.llm_calls for r in agent_results)
        avg_answer_len = sum(r.answer_length for r in agent_results) / len(agent_results)

        all_kw_found = sum(len(r.keywords_found) for r in agent_results)
        all_kw_total = sum(len(r.keywords_found) + len(r.keywords_missing) for r in agent_results)

        print(f"  Total time:       {total_time:.1f}s ({avg_time:.1f}s avg)")
        print(f"  Total tool calls: {total_tools} ({total_tools/len(agent_results):.1f} avg)")
        print(f"  Total LLM calls:  {total_llm} ({total_llm/len(agent_results):.1f} avg)")
        print(f"  Avg answer length: {avg_answer_len:.0f} chars")
        print(f"  Keyword coverage: {all_kw_found}/{all_kw_total} ({all_kw_found/all_kw_total*100:.0f}%)")

        # Per-question consistency
        for q in QUESTIONS:
            q_results = [r for r in agent_results if r.question_id == q["id"]]
            cons = tool_consistency(q_results)
            print(f"  Tool consistency ({q['id']}): {cons:.0%}")

        print()

    # Detailed tool calls comparison
    print_header("DETAILED TOOL CALLS PER QUESTION")
    for q in QUESTIONS:
        print(f"\n  {q['name']}:")
        for agent_label in ["Original", "LangChain"]:
            runs = [r for r in all_results if r.question_id == q["id"] and r.agent_type == agent_label]
            print(f"    {agent_label}:")
            for r in runs:
                tools_str = ", ".join(r.tool_names) if r.tool_names else "(none)"
                print(f"      Run {r.run_number}: [{r.tool_count} tools] {tools_str}")

    # Answer quality samples
    print()
    print_header("ANSWER QUALITY SAMPLES (first run of each)")
    for q in QUESTIONS:
        print(f"\n  {q['name']}:")
        for agent_label in ["Original", "LangChain"]:
            runs = [r for r in all_results if r.question_id == q["id"] and r.agent_type == agent_label]
            if runs:
                r = runs[0]
                preview = r.answer_text[:300].replace("\n", "\n    ") if r.answer_text else "(empty)"
                print(f"    [{agent_label}] ({r.answer_length} chars, {r.elapsed_seconds:.1f}s)")
                print(f"    {preview}")
                if r.answer_length > 300:
                    print(f"    ... ({r.answer_length - 300} more chars)")
                print(f"    Keywords found: {r.keywords_found}")
                print(f"    Keywords missing: {r.keywords_missing}")
                print()


if __name__ == "__main__":
    main()
