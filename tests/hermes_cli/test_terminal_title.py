import io

from hermes_cli.terminal_title import (
    TerminalTitleConfig,
    TerminalTitleManager,
    load_terminal_title_config,
    sanitize_title,
)


class TtyStringIO(io.StringIO):
    def isatty(self):
        return True


def test_load_terminal_title_config_from_display_section():
    cfg = load_terminal_title_config(
        {
            "display": {
                "terminal_title": {
                    "enabled": "yes",
                    "mode": "OSC",
                    "prefix": "H: ",
                    "fallback_title": "Hermes Agent",
                    "max_length": "25",
                    "update_on_start": "false",
                }
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.mode == "osc"
    assert cfg.prefix == "H: "
    assert cfg.fallback_title == "Hermes Agent"
    assert cfg.max_length == 25
    assert cfg.update_on_start is False


def test_sanitize_title_removes_control_chars_and_truncates():
    assert sanitize_title("  build\nHermes\tfeature  ", 20) == "build Hermes feature"
    assert sanitize_title("a" * 12, 10) == "aaaaaaaaa…"


def test_osc_backend_writes_title_escape():
    out = TtyStringIO()
    mgr = TerminalTitleManager(
        TerminalTitleConfig(enabled=True, mode="osc", prefix="Hermes: ", max_length=50),
        env={},
        stdout=out,
        now=lambda: 100.0,
    )

    assert mgr.set_context_title("terminal titles") is True
    assert out.getvalue() == "\033]0;Hermes: terminal titles\007"


def test_immediate_title_change_after_startup_is_not_rate_limited():
    out = TtyStringIO()
    mgr = TerminalTitleManager(
        TerminalTitleConfig(enabled=True, mode="osc", prefix="Hermes: ", max_length=50),
        env={},
        stdout=out,
        now=lambda: 100.0,
    )

    assert mgr.set_context_title(None) is True
    assert mgr.set_context_title("new project") is True
    assert out.getvalue() == "\033]0;Hermes\007\033]0;Hermes: new project\007"


def test_disabled_manager_is_noop():
    out = TtyStringIO()
    mgr = TerminalTitleManager(
        TerminalTitleConfig(enabled=False, mode="osc"),
        env={},
        stdout=out,
        now=lambda: 100.0,
    )

    assert mgr.set_context_title("ignored") is False
    assert out.getvalue() == ""


def test_non_tty_stdout_does_not_emit_escape_sequences():
    out = io.StringIO()
    mgr = TerminalTitleManager(
        TerminalTitleConfig(enabled=True, mode="osc"),
        env={},
        stdout=out,
        now=lambda: 100.0,
    )

    assert mgr.set_context_title("logs should stay clean") is False
    assert out.getvalue() == ""
