"""Run screenshot-to-code prompts through a local Codex CLI subscription."""

import asyncio
import base64
import json
import os
import re
import tempfile
from pathlib import Path
from typing import cast

from openai.types.chat import ChatCompletionMessageParam


_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"html": {"type": "string"}},
    "required": ["html"],
    "additionalProperties": False,
}

_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
_TIMEOUT_SECONDS = 600

_CLI_OUTPUT_INSTRUCTION = """
# Codex CLI adapter override

The app-specific file and image tool names mentioned above are unavailable in
this run. Do not inspect or modify local files and do not call tools. Apply the
request using the supplied text and attached images. Return exactly one complete standalone HTML document in the `html` field required by the output schema. For
an update, return the complete updated document rather than edit operations.
"""


def _write_data_image(data_url: str, path: Path) -> None:
    header, separator, encoded = data_url.partition(",")
    if not separator or ";base64" not in header:
        raise ValueError("Codex CLI only supports base64 image data URLs.")
    try:
        path.write_bytes(base64.b64decode(encoded, validate=True))
    except ValueError as exc:
        raise ValueError("Invalid base64 image data URL.") from exc


def prepare_codex_input(
    prompt_messages: list[ChatCompletionMessageParam],
    directory: Path,
) -> tuple[str, list[Path]]:
    sections: list[str] = []
    image_paths: list[Path] = []

    for message in prompt_messages:
        role = str(message.get("role", "user")).upper()
        content = message.get("content", "")
        parts: list[str] = []

        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
                    continue
                if part.get("type") != "image_url":
                    continue

                raw_image_url = cast(object, part.get("image_url"))
                image_url = (
                    cast(dict[str, object], raw_image_url)
                    if isinstance(raw_image_url, dict)
                    else None
                )
                url = image_url.get("url") if image_url else None
                if not isinstance(url, str) or not url.startswith("data:image/"):
                    raise ValueError("Codex CLI only supports local image data URLs.")
                header = url.split(",", 1)[0]
                mime_type = header.removeprefix("data:").split(";", 1)[0].lower()
                extension = _IMAGE_EXTENSIONS.get(mime_type)
                if extension is None:
                    raise ValueError(f"Unsupported Codex CLI image type: {mime_type}")
                image_path = directory / f"input-{len(image_paths) + 1}.{extension}"
                _write_data_image(url, image_path)
                image_paths.append(image_path)
                parts.append(f"[Attached image {len(image_paths)}]")

        sections.append(f"[{role}]\n" + "\n".join(parts))

    sections.append(_CLI_OUTPUT_INSTRUCTION.strip())
    return "\n\n".join(sections), image_paths


class CodexCliError(Exception):
    pass


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


def _safe_stderr_summary(stderr: bytes) -> str:
    lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
    summary = lines[-1] if lines else "Unknown Codex CLI error."
    summary = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|authorization)\b\s*[:=]\s*\S+",
        r"\1=[redacted]",
        summary,
    )
    summary = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[redacted]", summary)
    return summary[:300]


async def run_codex_cli(
    prompt_messages: list[ChatCompletionMessageParam],
    *,
    cli_path: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    executable = Path(cli_path).expanduser()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise CodexCliError(
            "Codex CLI executable was not found. Set CODEX_CLI_PATH to a valid executable."
        )
    if reasoning_effort and reasoning_effort not in _REASONING_EFFORTS:
        allowed = ", ".join(sorted(_REASONING_EFFORTS))
        raise CodexCliError(f"Invalid CODEX_REASONING_EFFORT. Use one of: {allowed}.")

    with tempfile.TemporaryDirectory(prefix="screenshot-to-code-codex-") as temp:
        directory = Path(temp)
        prompt, image_paths = prepare_codex_input(prompt_messages, directory)
        schema_path = directory / "output-schema.json"
        schema_path.write_text(json.dumps(_OUTPUT_SCHEMA), encoding="utf-8")

        command = [
            str(executable),
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--output-schema",
            str(schema_path),
            "-C",
            str(directory),
        ]
        if model:
            command.extend(["--model", model])
        if reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
        for image_path in image_paths:
            command.extend(["-i", str(image_path)])
        command.append("-")

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=directory,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise CodexCliError(
                "Codex CLI could not be started. Set CODEX_CLI_PATH to a valid executable."
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            await _stop_process(process)
            raise CodexCliError("Codex CLI timed out after 10 minutes.") from exc
        except BaseException:
            await _stop_process(process)
            raise

        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if any(
                marker in stderr_text.lower()
                for marker in ("authentication", "not logged in", "login required")
            ):
                raise CodexCliError(
                    "Codex CLI is not logged in. Run `codex login` and try again."
                )
            raise CodexCliError(f"Codex CLI failed: {_safe_stderr_summary(stderr)}")

        try:
            payload = json.loads(stdout.decode("utf-8"))
            html = payload["html"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise CodexCliError("Codex CLI returned invalid structured output.") from exc

        if not isinstance(html, str) or not re.search(
            r"<html\b[^>]*>.*</html>\s*$", html.strip(), re.DOTALL | re.IGNORECASE
        ):
            raise CodexCliError("Codex CLI did not return a complete HTML document.")
        return html.strip()
