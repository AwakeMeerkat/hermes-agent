import json
import time
from unittest.mock import MagicMock, patch

import cli as cli_module
from cli import HermesCLI


class TestGflashResearchPacket:
    def test_build_gflash_research_packet_searches_and_extracts_top_pages(self):
        cli = HermesCLI.__new__(HermesCLI)

        search_payload = json.dumps(
            {
                "success": True,
                "data": {
                    "web": [
                        {
                            "title": "First Result",
                            "url": "https://example.com/one",
                            "description": "First description",
                            "position": 1,
                        },
                        {
                            "title": "Second Result",
                            "url": "https://example.com/two",
                            "description": "Second description",
                            "position": 2,
                        },
                    ]
                },
            }
        )

        async def fake_extract(urls, format=None, use_llm_processing=True, model=None, min_length=None):
            assert urls == ["https://example.com/one", "https://example.com/two"]
            return json.dumps(
                {
                    "success": True,
                    "results": [
                        {
                            "title": "First Result",
                            "url": "https://example.com/one",
                            "content": "Page body one",
                        },
                        {
                            "title": "Second Result",
                            "url": "https://example.com/two",
                            "content": "Page body two",
                        },
                    ],
                }
            )

        with patch.object(cli_module, "web_search_tool", return_value=search_payload), \
             patch.object(cli_module, "web_extract_tool", side_effect=fake_extract):
            packet = cli._build_gflash_research_packet("best hermes agent workflows")

        assert "Search results" in packet
        assert "First Result" in packet
        assert "https://example.com/one" in packet
        assert "First description" in packet
        assert "Page body one" in packet
        assert "Second Result" in packet
        assert "Page body two" in packet

    def test_handle_gflash_command_uses_prefetched_research_packet(self):
        cli = HermesCLI.__new__(HermesCLI)
        cli._background_task_counter = 0
        cli._background_tasks = {}
        cli._sudo_password_callback = lambda: "secret"
        cli._approval_callback = lambda *_args, **_kwargs: "once"
        cli._secret_capture_callback = lambda *_args, **_kwargs: {}
        cli._agent_running = False
        cli._spinner_text = ""
        cli._app = None
        cli._invalidate = MagicMock()
        cli.bell_on_complete = False
        cli.final_response_markdown = "strip"
        cli._scrollback_box_width = lambda width=None: 80
        cli._build_gflash_research_packet = MagicMock(return_value="PACKET")

        seen = {}

        class FakeAgent:
            def __init__(self, **kwargs):
                seen["kwargs"] = kwargs
                self._print_fn = None
                self.thinking_callback = None

            def run_conversation(self, user_message, task_id=None):
                seen["user_message"] = user_message
                seen["task_id"] = task_id
                return {"final_response": "ANSWER"}

        class FakeThread:
            def __init__(self, target, daemon=False, name=None):
                self.target = target
                self.daemon = daemon
                self.name = name

            def start(self):
                self.target()

        with patch.dict(cli_module.os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False), \
             patch.object(cli_module, "AIAgent", FakeAgent), \
             patch.object(cli_module.threading, "Thread", FakeThread), \
             patch.object(cli_module, "_cprint"), \
             patch.object(cli_module, "ChatConsole") as chat_console:
            chat_console.return_value.print = MagicMock()
            cli._handle_gflash_command("/gflash hermes agents")

        deadline = time.time() + 2
        while "kwargs" not in seen and time.time() < deadline:
            time.sleep(0.01)

        assert seen["kwargs"]["enabled_toolsets"] == []
        assert "PACKET" in seen["user_message"]
        assert "User query: hermes agents" in seen["user_message"]
