from types import SimpleNamespace
from unittest.mock import MagicMock

from cli import HermesCLI


def _make_cli(update_on_start=True, existing_title=None, pending_title=None):
    cli = MagicMock()
    cli.session_id = "sid"
    cli._pending_title = pending_title
    cli._session_db = MagicMock()
    cli._session_db.get_session_title.return_value = existing_title
    cli._terminal_title = SimpleNamespace(
        config=SimpleNamespace(update_on_start=update_on_start)
    )
    cli._compact_early_title_source = HermesCLI._compact_early_title_source.__get__(cli, HermesCLI)
    cli._set_terminal_context_title = MagicMock()
    return cli


def test_early_turn_title_uses_short_summary_when_session_is_untitled():
    cli = _make_cli(existing_title=None)

    HermesCLI._set_early_turn_title(cli, "Build a GPU utilization percentage applet and add it to both taskbars")

    cli._set_terminal_context_title.assert_called_once_with("GPU utilization")


def test_early_turn_title_gets_even_shorter_for_caps_heavy_prompts():
    cli = _make_cli(existing_title=None)

    HermesCLI._set_early_turn_title(cli, "Build a GPU UTILIZATION applet for the taskbars")

    called_title = cli._set_terminal_context_title.call_args.args[0]
    assert len(called_title) <= 16
    assert called_title.startswith("GPU UTILIZATION") or called_title.startswith("GPU")


def test_early_turn_title_skips_when_session_already_has_title():
    cli = _make_cli(existing_title="Existing title")

    HermesCLI._set_early_turn_title(cli, "Build a GPU utilization applet")

    cli._set_terminal_context_title.assert_not_called()


def test_early_turn_title_skips_when_pending_title_exists():
    cli = _make_cli(existing_title=None, pending_title="queued title")

    HermesCLI._set_early_turn_title(cli, "Build a GPU utilization applet")

    cli._set_terminal_context_title.assert_not_called()
