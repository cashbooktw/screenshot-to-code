import asyncio
import base64
import importlib.util
import json
import os
import sys
from pathlib import Path

import codex_cli
import pytest


def test_codex_cli_module_exists() -> None:
    assert importlib.util.find_spec("codex_cli") is not None


def _data_url(mime_type: str, content: bytes) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _write_fake_codex(path: Path, output: str, capture_path: Path) -> None:
    path.write_text(
        f"""#!{sys.executable}
import base64
import json
import os
import pathlib
import sys

args = sys.argv[1:]
image_paths = [args[index + 1] for index, value in enumerate(args) if value == "-i"]
schema_path = args[args.index("--output-schema") + 1]
capture = {{
    "args": args,
    "prompt": sys.stdin.read(),
    "images": [base64.b64encode(pathlib.Path(path).read_bytes()).decode("ascii") for path in image_paths],
    "schema": json.loads(pathlib.Path(schema_path).read_text()),
    "backend_secret": os.environ.get("BACKEND_SECRET"),
}}
pathlib.Path({str(capture_path)!r}).write_text(json.dumps(capture))
print({output!r})
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_prepare_codex_input_flattens_roles_and_writes_images(tmp_path: Path) -> None:
    prompt, image_paths = codex_cli.prepare_codex_input(
        [
            {"role": "system", "content": "System rules"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _data_url("image/png", b"first-image")
                        },
                    },
                    {"type": "text", "text": "Build this page"},
                ],
            },
            {"role": "assistant", "content": "Earlier result"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _data_url("image/jpeg", b"second-image")
                        },
                    },
                    {"type": "text", "text": "Make it darker"},
                ],
            },
        ],
        tmp_path,
    )

    assert "[SYSTEM]\nSystem rules" in prompt
    assert "[USER]\n[Attached image 1]\nBuild this page" in prompt
    assert "[ASSISTANT]\nEarlier result" in prompt
    assert "[USER]\n[Attached image 2]\nMake it darker" in prompt
    assert "Return exactly one complete standalone HTML document" in prompt
    assert [path.name for path in image_paths] == ["input-1.png", "input-2.jpg"]
    assert image_paths[0].read_bytes() == b"first-image"
    assert image_paths[1].read_bytes() == b"second-image"


@pytest.mark.asyncio
async def test_run_codex_cli_uses_safe_flags_and_returns_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture_path = tmp_path / "capture.json"
    cli_path = tmp_path / "codex"
    expected_html = "<!DOCTYPE html><html><body>Done</body></html>"
    _write_fake_codex(
        cli_path, json.dumps({"html": expected_html}), capture_path
    )
    monkeypatch.setenv("BACKEND_SECRET", "must-not-reach-codex")

    result = await codex_cli.run_codex_cli(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _data_url("image/png", b"screenshot")
                        },
                    },
                    {"type": "text", "text": "Build it"},
                ],
            }
        ],
        cli_path=str(cli_path),
        model="test-model",
        reasoning_effort="high",
    )

    assert result == expected_html
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    args = capture["args"]
    assert args[0] == "exec"
    assert ["--ephemeral", "--sandbox", "read-only"] == args[1:4]
    assert "--skip-git-repo-check" in args
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert 'approval_policy="never"' in args
    assert ["--color", "never"] == args[args.index("--color") :][:2]
    assert ["--model", "test-model"] == args[args.index("--model") :][:2]
    assert 'model_reasoning_effort="high"' in args
    assert args[-1] == "-"
    assert "Build it" in capture["prompt"]
    assert capture["images"] == [
        base64.b64encode(b"screenshot").decode("ascii")
    ]
    assert capture["schema"] == {
        "type": "object",
        "properties": {"html": {"type": "string"}},
        "required": ["html"],
        "additionalProperties": False,
    }
    assert capture["backend_secret"] is None


@pytest.mark.asyncio
async def test_run_codex_cli_maps_login_failure_to_actionable_error(
    tmp_path: Path,
) -> None:
    cli_path = tmp_path / "codex"
    cli_path.write_text(
        f"""#!{sys.executable}
import sys
print("Authentication required", file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    cli_path.chmod(0o755)

    with pytest.raises(codex_cli.CodexCliError, match=r"codex login"):
        await codex_cli.run_codex_cli(
            [{"role": "user", "content": "Build a page"}],
            cli_path=str(cli_path),
        )


@pytest.mark.asyncio
async def test_run_codex_cli_redacts_secrets_from_stderr(tmp_path: Path) -> None:
    cli_path = tmp_path / "codex"
    cli_path.write_text(
        f"""#!{sys.executable}
import sys
print("request failed: api_key=sk-sensitive-value", file=sys.stderr)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    cli_path.chmod(0o755)

    with pytest.raises(codex_cli.CodexCliError) as error:
        await codex_cli.run_codex_cli(
            [{"role": "user", "content": "Build a page"}],
            cli_path=str(cli_path),
        )

    assert "request failed" in str(error.value)
    assert "sk-sensitive-value" not in str(error.value)


@pytest.mark.asyncio
async def test_run_codex_cli_maps_launch_failure_to_actionable_error(
    tmp_path: Path,
) -> None:
    cli_path = tmp_path / "codex"
    cli_path.write_text("not an executable format", encoding="utf-8")
    cli_path.chmod(0o755)

    with pytest.raises(codex_cli.CodexCliError, match="CODEX_CLI_PATH"):
        await codex_cli.run_codex_cli(
            [{"role": "user", "content": "Build a page"}],
            cli_path=str(cli_path),
        )


@pytest.mark.asyncio
async def test_run_codex_cli_times_out_and_terminates_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminated_path = tmp_path / "terminated"
    cli_path = tmp_path / "codex"
    cli_path.write_text(
        f"""#!{sys.executable}
import os
import pathlib
import signal
import time

def stop(*_):
    pathlib.Path({str(terminated_path)!r}).write_text("yes")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
time.sleep(60)
""",
        encoding="utf-8",
    )
    cli_path.chmod(0o755)
    monkeypatch.setattr(codex_cli, "_TIMEOUT_SECONDS", 1.0)

    with pytest.raises(codex_cli.CodexCliError, match="timed out"):
        await codex_cli.run_codex_cli(
            [{"role": "user", "content": "Build a page"}],
            cli_path=str(cli_path),
        )

    assert terminated_path.read_text() == "yes"


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("not json", "invalid structured output"),
        (json.dumps({"html": "<div>fragment</div>"}), "complete HTML document"),
    ],
)
@pytest.mark.asyncio
async def test_run_codex_cli_rejects_invalid_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
    message: str,
) -> None:
    cli_path = tmp_path / "codex"
    _write_fake_codex(cli_path, output, tmp_path / "capture.json")

    with pytest.raises(codex_cli.CodexCliError, match=message):
        await codex_cli.run_codex_cli(
            [{"role": "user", "content": "Build a page"}],
            cli_path=str(cli_path),
        )


@pytest.mark.asyncio
async def test_run_codex_cli_validates_executable_and_reasoning_effort(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-codex"
    with pytest.raises(codex_cli.CodexCliError, match="CODEX_CLI_PATH"):
        await codex_cli.run_codex_cli([], cli_path=str(missing))

    cli_path = tmp_path / "codex"
    cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
    cli_path.chmod(0o755)
    with pytest.raises(codex_cli.CodexCliError, match="CODEX_REASONING_EFFORT"):
        await codex_cli.run_codex_cli(
            [], cli_path=str(cli_path), reasoning_effort="extreme"
        )


@pytest.mark.asyncio
async def test_run_codex_cli_resolves_relative_executable_before_chdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_path = tmp_path / "codex"
    expected_html = "<html><body>Relative path</body></html>"
    _write_fake_codex(
        cli_path,
        json.dumps({"html": expected_html}),
        tmp_path / "capture.json",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")

    result = await codex_cli.run_codex_cli(
        [{"role": "user", "content": "Build a page"}],
        cli_path="codex",
    )

    assert result == expected_html


def test_prepare_codex_input_rejects_invalid_image_data(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base64"):
        codex_cli.prepare_codex_input(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,%%%"},
                        }
                    ],
                }
            ],
            tmp_path,
        )

    with pytest.raises(ValueError, match="Unsupported"):
        codex_cli.prepare_codex_input(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _data_url("image/svg+xml", b"<svg/>")
                            },
                        }
                    ],
                }
            ],
            tmp_path,
        )


@pytest.mark.asyncio
async def test_run_codex_cli_cancellation_terminates_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started_path = tmp_path / "started"
    terminated_path = tmp_path / "terminated"
    cli_path = tmp_path / "codex"
    cli_path.write_text(
        f"""#!{sys.executable}
import os
import pathlib
import signal
import time

pathlib.Path({str(started_path)!r}).write_text("yes")

def stop(*_):
    pathlib.Path({str(terminated_path)!r}).write_text("yes")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
time.sleep(60)
""",
        encoding="utf-8",
    )
    cli_path.chmod(0o755)

    task = asyncio.create_task(
        codex_cli.run_codex_cli(
            [{"role": "user", "content": "Build a page"}],
            cli_path=str(cli_path),
        )
    )
    for _ in range(100):
        if started_path.exists():
            break
        await asyncio.sleep(0.01)
    assert started_path.exists()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert terminated_path.read_text() == "yes"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
@pytest.mark.asyncio
async def test_run_codex_cli_timeout_terminates_descendant_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child_pid_path = tmp_path / "child-pid"
    child_terminated_path = tmp_path / "child-terminated"
    cli_path = tmp_path / "codex"
    cli_path.write_text(
        f"""#!{sys.executable}
import os
import pathlib
import subprocess
import sys
import time

child_code = '''
import os
import pathlib
import signal
import time

def stop(*_):
    pathlib.Path({str(child_terminated_path)!r}).write_text("yes")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
pathlib.Path({str(child_pid_path)!r}).write_text(str(os.getpid()))
time.sleep(60)
'''
subprocess.Popen(
    [sys.executable, "-c", child_code],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(60)
""",
        encoding="utf-8",
    )
    cli_path.chmod(0o755)
    monkeypatch.setattr(codex_cli, "_TIMEOUT_SECONDS", 1.0)

    try:
        with pytest.raises(codex_cli.CodexCliError, match="timed out"):
            await codex_cli.run_codex_cli(
                [{"role": "user", "content": "Build a page"}],
                cli_path=str(cli_path),
            )

        assert child_terminated_path.read_text() == "yes"
    finally:
        if child_pid_path.exists() and not child_terminated_path.exists():
            try:
                os.kill(int(child_pid_path.read_text()), 9)
            except ProcessLookupError:
                pass
