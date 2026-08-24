from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.chat import ChatCompletionMessageParam

from llm import Llm
from routes.generate_code import (
    AgenticGenerationStage,
    CodeGenerationMiddleware,
    ExtractedParams,
    ModelSelectionStage,
    PipelineContext,
)


def _extracted_params() -> ExtractedParams:
    return ExtractedParams(
        stack="html_tailwind",
        input_mode="text",
        should_generate_images=True,
        openai_api_key="openai-key",
        anthropic_api_key="anthropic-key",
        gemini_api_key="gemini-key",
        replicate_api_key="replicate-key",
        openai_base_url=None,
        generation_type="create",
        prompt={"text": "Build a page", "images": [], "videos": []},
        history=[],
        file_state=None,
        option_codes=[],
    )


@pytest.mark.asyncio
async def test_code_generation_always_selects_one_codex_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbid_model_selection(*args: Any, **kwargs: Any) -> list[Llm]:
        raise AssertionError("legacy provider model selection must not run")

    expected_html = "<html><body>Codex</body></html>"

    async def fake_process_variants(
        self: AgenticGenerationStage,
        variant_models: list[Llm],
        prompt_messages: list[ChatCompletionMessageParam],
    ) -> dict[int, str]:
        assert variant_models == [Llm.CODEX_CLI]
        return {0: expected_html}

    monkeypatch.setattr(ModelSelectionStage, "select_models", forbid_model_selection)
    monkeypatch.setattr(
        AgenticGenerationStage, "process_variants", fake_process_variants
    )

    context = PipelineContext(websocket=MagicMock())
    throw_error = AsyncMock()
    context.ws_comm = cast(
        Any,
        SimpleNamespace(send_message=AsyncMock(), throw_error=throw_error),
    )
    context.extracted_params = _extracted_params()
    context.prompt_messages = [{"role": "user", "content": "Build a page"}]
    next_func = AsyncMock()

    await CodeGenerationMiddleware().process(context, next_func)

    assert context.variant_models == [Llm.CODEX_CLI]
    assert context.completions == [expected_html]
    next_func.assert_awaited_once()
    throw_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_codex_variant_bypasses_agent_and_records_unpriced_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_html = "<!DOCTYPE html><html><body>Done</body></html>"
    prompt_messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "Build a page"}
    ]
    calls: list[tuple[list[ChatCompletionMessageParam], dict[str, Any]]] = []

    async def fake_codex_cli(
        messages: list[ChatCompletionMessageParam], **kwargs: Any
    ) -> str:
        calls.append((messages, kwargs))
        return expected_html

    class ForbiddenAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("Agent/provider factory must not be used")

    recorder = MagicMock()
    recorder.record_run_end = AsyncMock()
    monkeypatch.setattr("routes.generate_code.run_codex_cli", fake_codex_cli)
    monkeypatch.setattr("routes.generate_code.Agent", ForbiddenAgent)
    monkeypatch.setattr("routes.generate_code.AgentRunRecorder", lambda **_: recorder)
    monkeypatch.setattr("routes.generate_code.CODEX_CLI_PATH", "/custom/codex")
    monkeypatch.setattr("routes.generate_code.CODEX_MODEL", "codex-model")
    monkeypatch.setattr("routes.generate_code.CODEX_REASONING_EFFORT", "high")

    send_message = AsyncMock()
    stage = AgenticGenerationStage(
        send_message=send_message,
        openai_api_key="present-but-unused",
        openai_base_url=None,
        anthropic_api_key="present-but-unused",
        gemini_api_key="present-but-unused",
        replicate_api_key="present-but-unused",
        should_generate_images=True,
        file_state=None,
        asset_base_url="",
        option_codes=[],
    )

    result = await stage._run_variant(0, Llm.CODEX_CLI, prompt_messages)

    assert result == expected_html
    assert calls == [
        (
            prompt_messages,
            {
                "cli_path": "/custom/codex",
                "model": "codex-model",
                "reasoning_effort": "high",
            },
        )
    ]
    recorder.record_run_start.assert_called_once_with(Llm.CODEX_CLI, prompt_messages)
    recorder.record_llm_request.assert_called_once()
    recorder.record_llm_response.assert_called_once_with(expected_html, [], None)
    recorder.record_set_code.assert_called_once_with(len(expected_html), "codex_cli")
    recorder.record_run_end.assert_awaited_once_with(
        "completed", final_html=expected_html
    )
    assert send_message.await_args_list[-2].args[:3] == (
        "setCode",
        expected_html,
        0,
    )
    assert send_message.await_args_list[-1].args[:3] == (
        "variantComplete",
        "Variant generation complete",
        0,
    )
