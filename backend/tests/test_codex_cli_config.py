from collections.abc import Callable

import config


def test_explicit_codex_cli_path_wins_over_path_lookup() -> None:
    resolver = getattr(config, "resolve_codex_cli_path", None)
    assert isinstance(resolver, Callable)

    assert resolver("/custom/bin/codex", lambda _: "/path/bin/codex") == (
        "/custom/bin/codex"
    )


def test_codex_cli_path_uses_path_lookup_when_unset() -> None:
    resolver = getattr(config, "resolve_codex_cli_path", None)
    assert isinstance(resolver, Callable)

    assert resolver(None, lambda command: f"/path/bin/{command}") == (
        "/path/bin/codex"
    )
