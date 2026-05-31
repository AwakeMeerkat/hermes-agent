"""Best-effort terminal/tab title updates for the classic Hermes CLI.

The public entry point is :class:`TerminalTitleManager`.  It hides terminal
emulator differences behind a small, failure-tolerant interface so title
updates never interfere with the conversation loop.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Mapping, MutableMapping, TextIO

logger = logging.getLogger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class TerminalTitleConfig:
    enabled: bool = True
    mode: str = "auto"  # auto | konsole | tmux | osc | off
    prefix: str = ""
    fallback_title: str = "Hermes"
    max_length: int = 32
    update_on_start: bool = True


def load_terminal_title_config(config: Mapping | None) -> TerminalTitleConfig:
    """Build a normalized terminal-title config from the full Hermes config."""

    display = (config or {}).get("display", {}) if isinstance(config, Mapping) else {}
    raw = display.get("terminal_title", {}) if isinstance(display, Mapping) else {}
    if raw is None:
        raw = {}
    if isinstance(raw, bool):
        raw = {"enabled": raw}
    if not isinstance(raw, Mapping):
        raw = {}

    def _bool(name: str, default: bool) -> bool:
        value = raw.get(name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        return bool(value)

    def _str(name: str, default: str) -> str:
        value = raw.get(name, default)
        return str(value) if value is not None else default

    try:
        max_length = int(raw.get("max_length", 32))
    except (TypeError, ValueError):
        max_length = 32
    max_length = max(10, min(max_length, 120))

    mode = _str("mode", "auto").strip().lower() or "auto"
    if mode not in {"auto", "konsole", "tmux", "osc", "off"}:
        mode = "auto"

    return TerminalTitleConfig(
        enabled=_bool("enabled", True),
        mode=mode,
        prefix=_str("prefix", ""),
        fallback_title=_str("fallback_title", "Hermes") or "Hermes",
        max_length=max_length,
        update_on_start=_bool("update_on_start", True),
    )


def sanitize_title(value: str, max_length: int = 50) -> str:
    """Return a terminal-safe single-line title."""

    title = _CONTROL_CHARS_RE.sub(" ", str(value or ""))
    title = _WHITESPACE_RE.sub(" ", title).strip()
    if max_length > 0 and len(title) > max_length:
        title = title[: max(1, max_length - 1)].rstrip() + "…"
    return title


class TerminalTitleManager:
    """Update the current terminal/tab title without surfacing failures.

    Backends:
    - Konsole DBus when Konsole exposes session handles.
    - tmux window rename when running inside tmux.
    - Generic OSC title escape for most graphical terminals.
    """

    def __init__(
        self,
        config: TerminalTitleConfig,
        *,
        env: Mapping[str, str] | None = None,
        stdout: TextIO | None = None,
        now=time.monotonic,
    ) -> None:
        self.config = config
        self.env = env if env is not None else os.environ
        self.stdout = stdout if stdout is not None else sys.stdout
        self._now = now
        self._last_title: str | None = None
        self._last_update = 0.0

    @classmethod
    def from_config(cls, config: Mapping | None) -> "TerminalTitleManager":
        return cls(load_terminal_title_config(config))

    def set_context_title(self, context: str | None) -> bool:
        """Set title to prefix + context, or fallback title when context is empty."""

        context = sanitize_title(context or "", self.config.max_length)
        if context:
            title = f"{self.config.prefix}{context}"
        else:
            title = self.config.fallback_title
        return self.set_title(title)

    def set_title(self, title: str | None, *, force: bool = False) -> bool:
        if not self.config.enabled or self.config.mode == "off":
            return False

        clean = sanitize_title(title or self.config.fallback_title, self.config.max_length + len(self.config.prefix) + 5)
        if not clean:
            return False
        if clean == self._last_title and not force:
            return True

        try:
            ok = self._set_title(clean)
        except Exception:
            logger.debug("Terminal title update failed", exc_info=True)
            ok = False
        if ok:
            self._last_title = clean
            self._last_update = self._now()
        return ok

    def _set_title(self, title: str) -> bool:
        mode = self.config.mode
        if mode in {"auto", "konsole"} and self._can_use_konsole():
            if self._set_konsole_title(title):
                return True
            if mode == "konsole":
                return False

        if mode in {"auto", "tmux"} and self.env.get("TMUX"):
            if self._set_tmux_title(title):
                return True
            if mode == "tmux":
                return False

        if mode in {"auto", "osc"}:
            return self._set_osc_title(title)
        return False

    def _can_use_konsole(self) -> bool:
        return bool(self.env.get("KONSOLE_DBUS_SERVICE") and self.env.get("KONSOLE_DBUS_SESSION"))

    def _set_konsole_title(self, title: str) -> bool:
        qdbus = shutil.which("qdbus") or shutil.which("qdbus6") or shutil.which("qdbus-qt5")
        if not qdbus:
            return False
        service = self.env.get("KONSOLE_DBUS_SERVICE")
        session = self.env.get("KONSOLE_DBUS_SESSION")
        if not service or not session:
            return False

        completed = subprocess.run(
            [
                qdbus,
                service,
                session,
                "org.kde.konsole.Session.setTabTitleFormat",
                "0",
                title,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1.5,
            check=False,
        )
        return completed.returncode == 0

    def _set_tmux_title(self, title: str) -> bool:
        tmux = shutil.which("tmux")
        if tmux:
            try:
                completed = subprocess.run(
                    [tmux, "rename-window", title],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                    check=False,
                )
                if completed.returncode == 0:
                    return True
            except Exception:
                logger.debug("tmux rename-window failed", exc_info=True)

        # tmux also understands the xterm window-title sequence when
        # allow-rename is enabled.  It is harmless when unsupported.
        return self._write_escape(f"\033k{title}\033\\")

    def _set_osc_title(self, title: str) -> bool:
        return self._write_escape(f"\033]0;{title}\007")

    def _write_escape(self, seq: str) -> bool:
        if not hasattr(self.stdout, "write"):
            return False
        # Avoid dumping raw escapes into non-interactive logs/pipes. Tests can
        # pass a StringIO that lacks isatty; that still exercises formatting.
        isatty = getattr(self.stdout, "isatty", None)
        if callable(isatty):
            try:
                if not isatty():
                    return False
            except Exception:
                return False
        self.stdout.write(seq)
        flush = getattr(self.stdout, "flush", None)
        if callable(flush):
            flush()
        return True
