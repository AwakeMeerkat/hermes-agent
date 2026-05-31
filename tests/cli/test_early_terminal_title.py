from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def _mock_llm_response(title):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = title
    return mock_response


def test_early_turn_title_uses_llm_summary_when_session_is_untitled():
    cli = _make_cli(existing_title=None)

    with patch("agent.auxiliary_client.call_llm", return_value=_mock_llm_response("Move memories to skills")):
        HermesCLI._set_early_turn_title(cli, "Great, rather than just remove those low priority entries, can you go ahead and move them to skills?")

    cli._set_terminal_context_title.assert_called_once_with("Move memories to skills")


def test_early_turn_title_strips_quotes_from_llm_output():
    cli = _make_cli(existing_title=None)

    with patch("agent.auxiliary_client.call_llm", return_value=_mock_llm_response('"Fix GPU applet"')):
        HermesCLI._set_early_turn_title(cli, "Fix the GPU applet in the taskbar")

    cli._set_terminal_context_title.assert_called_once_with("Fix GPU applet")


def test_early_turn_title_strips_title_prefix_from_llm_output():
    cli = _make_cli(existing_title=None)

    with patch("agent.auxiliary_client.call_llm", return_value=_mock_llm_response("Title: Debug Python Import")):
        HermesCLI._set_early_turn_title(cli, "Why does my Python import fail?")

    cli._set_terminal_context_title.assert_called_once_with("Debug Python Import")


def test_early_turn_title_falls_back_to_truncation_on_llm_failure():
    cli = _make_cli(existing_title=None)

    with patch("agent.auxiliary_client.call_llm", side_effect=RuntimeError("no provider")):
        HermesCLI._set_early_turn_title(cli, "Build a GPU utilization applet")

    cli._set_terminal_context_title.assert_called_once_with("Build a GPU utilization")


def test_early_turn_title_falls_back_to_truncation_for_caps_heavy_prompts():
    cli = _make_cli(existing_title=None)

    with patch("agent.auxiliary_client.call_llm", side_effect=RuntimeError("no provider")):
        HermesCLI._set_early_turn_title(cli, "Build a GPU UTILIZATION applet for the taskbars")

    called_title = cli._set_terminal_context_title.call_args.args[0]
    assert len(called_title) <= 30


def test_early_turn_title_skips_when_session_already_has_title():
    cli = _make_cli(existing_title="Existing title")

    HermesCLI._set_early_turn_title(cli, "Build a GPU utilization applet")

    cli._set_terminal_context_title.assert_not_called()


def test_early_turn_title_skips_when_pending_title_exists():
    cli = _make_cli(existing_title=None, pending_title="queued title")

    HermesCLI._set_early_turn_title(cli, "Build a GPU utilization applet")

    cli._set_terminal_context_title.assert_not_called()
