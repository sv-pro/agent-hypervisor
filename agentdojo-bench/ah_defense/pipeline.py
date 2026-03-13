"""
pipeline.py — AgentDojo BasePipelineElement subclasses for Agent Hypervisor.

Implements two pipeline elements that work together to defend against
prompt injection:

  AHInputSanitizer (post-ToolsExecutor, pre-LLM):
    - Canonicalizes tool output content (strips injection patterns)
    - Wraps outputs with AH trust metadata
    - Marks all tool outputs as tainted in shared TaintState

  AHTaintGuard (post-LLM, before next ToolsExecutor iteration):
    - Reads LLM's proposed tool calls from last assistant message
    - Validates each call against IntentValidator + TaintState
    - Removes blocked calls (or raises AbortAgentError if all calls blocked)

Core architectural guarantee: no LLM call occurs in either element.
Security decisions are O(1) manifest lookups + regex passes only.

Pipeline assembly:
  ToolsExecutionLoop([
      ToolsExecutor(formatter),
      AHInputSanitizer(taint_state, canonicalizer),
      llm,
      AHTaintGuard(taint_state, intent_validator),
  ])
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor, tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.types import (
    ChatMessage,
    get_text_content_as_str,
    text_content_block_from_string,
)

from ah_defense.canonicalizer import Canonicalizer
from ah_defense.intent_validator import IntentValidator
from ah_defense.taint_tracker import TaintState

logger = logging.getLogger(__name__)


class AHInputSanitizer(BasePipelineElement):
    """
    Post-ToolsExecutor, pre-LLM sanitizer.

    When tool results arrive in the messages list:
    1. Canonicalize each tool result's text content (strip injection patterns)
    2. Wrap content with AH trust metadata envelope
    3. Mark the tool call as tainted in the shared TaintState

    The LLM receives sanitized + trust-tagged content, reducing the surface
    area for prompt injection while making trust boundaries explicit.
    """

    name = "ah_input_sanitizer"

    def __init__(
        self,
        taint_state: TaintState,
        canonicalizer: Canonicalizer | None = None,
        wrap_trust_metadata: bool = True,
    ) -> None:
        """
        Args:
            taint_state: Shared taint state for this pipeline execution.
            canonicalizer: Canonicalizer instance. Creates a default one if None.
            wrap_trust_metadata: Whether to wrap tool outputs with AH trust envelope.
                                 Set to False for ablation studies.
        """
        self.taint_state = taint_state
        self.canonicalizer = canonicalizer or Canonicalizer()
        self.wrap_trust_metadata = wrap_trust_metadata

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        if not messages:
            return query, runtime, env, messages, extra_args

        # Find the trailing run of tool result messages
        # (ToolsExecutor appends them all at once)
        tool_indices: list[int] = []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "tool":
                tool_indices.append(i)
            else:
                break

        if not tool_indices:
            return query, runtime, env, messages, extra_args

        messages = list(messages)  # make mutable copy

        for idx in tool_indices:
            msg = messages[idx]
            # Deep copy to avoid mutating shared message objects
            msg = deepcopy(msg)

            # Mark this tool result as tainted
            tool_call_id = msg.get("tool_call_id") or f"call_{idx}"
            tool_name = msg.get("tool_call", {}).get("function", "unknown") if msg.get("tool_call") else "unknown"
            self.taint_state.mark_tainted(tool_call_id, tool_name)

            # Canonicalize content blocks
            new_content = []
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    raw_text = block.get("content", "")
                    clean_text = self.canonicalizer.canonicalize(raw_text)
                    if self.wrap_trust_metadata:
                        clean_text = self.canonicalizer.wrap_with_trust_metadata(
                            clean_text, source=f"tool:{tool_name}"
                        )
                    new_content.append(text_content_block_from_string(clean_text))
                else:
                    new_content.append(block)

            msg["content"] = new_content
            messages[idx] = msg

            logger.debug(
                "AHInputSanitizer: tainted and canonicalized tool result "
                "for call_id=%s tool=%s", tool_call_id, tool_name
            )

        return query, runtime, env, messages, extra_args


class AHTaintGuard(BasePipelineElement):
    """
    Post-LLM taint guard.

    After the LLM proposes tool calls (assistant message with tool_calls),
    validates each proposed call against the IntentValidator and TaintState.

    Blocked calls are removed from the assistant message. If all proposed
    calls are blocked, an error tool result is injected so the LLM knows
    why the action was refused (and may recover gracefully).

    This implements the TaintContainmentLaw:
        tainted_context + external_side_effect_tool → BLOCKED
    """

    name = "ah_taint_guard"

    def __init__(
        self,
        taint_state: TaintState,
        intent_validator: IntentValidator,
    ) -> None:
        """
        Args:
            taint_state: Shared taint state for this pipeline execution.
            intent_validator: Validator loaded with the suite's World Manifest.
        """
        self.taint_state = taint_state
        self.intent_validator = intent_validator

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        if not messages:
            return query, runtime, env, messages, extra_args

        last = messages[-1]
        if last["role"] != "assistant":
            return query, runtime, env, messages, extra_args

        tool_calls = last.get("tool_calls")
        if not tool_calls:
            return query, runtime, env, messages, extra_args

        allowed_calls = []
        denied_calls = []

        for tc in tool_calls:
            tool_name = tc.function if hasattr(tc, "function") else tc.get("function", "")
            result = self.intent_validator.validate(tool_name, self.taint_state)

            if result.verdict == "allow":
                allowed_calls.append(tc)
                logger.debug("AHTaintGuard: ALLOW %s", tool_name)
            else:
                denied_calls.append((tc, result))
                logger.info(
                    "AHTaintGuard: DENY %s — %s", tool_name, result.reason
                )

        if not denied_calls:
            return query, runtime, env, messages, extra_args

        # Mutate the assistant message: remove blocked tool calls
        messages = list(messages)
        last = deepcopy(last)

        if allowed_calls:
            last["tool_calls"] = allowed_calls
        else:
            # All calls blocked — clear tool_calls so the loop exits
            # and inject a synthetic error message so the LLM understands
            last["tool_calls"] = None

        messages[-1] = last

        # Inject synthetic tool result messages for denied calls
        # This gives the LLM feedback that the action was blocked
        from agentdojo.types import ChatToolResultMessage
        for tc, result in denied_calls:
            call_id = tc.id if hasattr(tc, "id") else tc.get("id", "blocked")
            error_msg = ChatToolResultMessage(
                role="tool",
                content=[text_content_block_from_string(
                    f"[AH SECURITY] Action blocked by Agent Hypervisor: {result.reason}"
                )],
                tool_call_id=call_id,
                tool_call=tc,
                error=result.reason,
            )
            messages.append(error_msg)

        return query, runtime, env, messages, extra_args


def build_ah_pipeline(
    llm: BasePipelineElement,
    suite_name: str,
    system_message: str,
    manifests_dir: str | Path | None = None,
    wrap_trust_metadata: bool = True,
    aggressive_canonicalization: bool = False,
) -> "BasePipelineElement":
    """
    Construct the full Agent Hypervisor pipeline for a given suite.

    Pipeline structure:
        [SystemMessage] → [InitQuery] → [LLM] →
        ToolsExecutionLoop([
            ToolsExecutor,
            AHInputSanitizer,   ← canonicalize + taint-mark tool outputs
            LLM,                ← propose next tool calls
            AHTaintGuard,       ← validate calls against taint + manifest
        ])

    Args:
        llm: The LLM pipeline element to use.
        suite_name: AgentDojo suite name (workspace, travel, banking, slack).
        system_message: System prompt text.
        manifests_dir: Path to directory containing manifest YAML files.
                       Defaults to ah_defense/manifests/.
        wrap_trust_metadata: Whether to wrap tool outputs with AH trust envelope.
        aggressive_canonicalization: Whether to use aggressive canonicalization
                                      (may reduce utility, increases security).

    Returns:
        A configured AgentPipeline ready for benchmarking.
    """
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline

    # Shared state for this pipeline execution
    taint_state = TaintState()
    canonicalizer = Canonicalizer(aggressive=aggressive_canonicalization)
    intent_validator = IntentValidator.for_suite(suite_name, manifests_dir)

    # Pipeline elements
    system_msg = SystemMessage(system_message)
    init_query = InitQuery()
    input_sanitizer = AHInputSanitizer(taint_state, canonicalizer, wrap_trust_metadata)
    taint_guard = AHTaintGuard(taint_state, intent_validator)

    tools_loop = ToolsExecutionLoop([
        ToolsExecutor(tool_result_to_str),
        input_sanitizer,
        llm,
        taint_guard,
    ])

    pipeline = AgentPipeline([
        system_msg,
        init_query,
        llm,
        tools_loop,
    ])
    pipeline.name = f"agent_hypervisor-{suite_name}"

    return pipeline
