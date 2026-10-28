"""
Unit and integration tests for Step C1: AI Agent Loop and Tool Registry.
"""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, patch

from app.agent_tools import (
    Tool,
    ToolRegistry,
    default_registry,
    build_default_registry,
)
from app.agent_loop import (
    run_agent_loop,
    AgentResult,
    record_active_task_action,
    get_active_task_memory,
    format_step_description,
    _active_task_memory,
)


class TestC1ToolRegistry:
    def test_all_11_tools_registered(self):
        tools = default_registry.all_tools()
        tool_names = {t.name for t in tools}
        expected = {
            "create_task",
            "complete_task",
            "delete_task",
            "remember_fact",
            "forget_fact",
            "search_web",
            "fetch_page",
            "list_devices",
            "send_note",
            "ring_phone",
            "open_url",
        }
        assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"

    def test_tool_risk_levels(self):
        # Risk 0: read-only
        assert default_registry.get("search_web").risk_level == 0
        assert default_registry.get("fetch_page").risk_level == 0
        assert default_registry.get("list_devices").risk_level == 0

        # Risk 1: safe side-effect
        assert default_registry.get("create_task").risk_level == 1
        assert default_registry.get("remember_fact").risk_level == 1

        # Risk 2: confirm
        assert default_registry.get("complete_task").risk_level == 2
        assert default_registry.get("forget_fact").risk_level == 2
        assert default_registry.get("send_note").risk_level == 2
        assert default_registry.get("open_url").risk_level == 2

        # Risk 3: sensitive always confirm
        assert default_registry.get("delete_task").risk_level == 3
        assert default_registry.get("ring_phone").risk_level == 3

    def test_schema_validation_valid_and_invalid(self):
        create_task_tool = default_registry.get("create_task")
        # Valid
        assert create_task_tool.validate_args({"title": "Study Python", "due_date": "tomorrow at 5pm"}) == []
        # Missing required title
        errs = create_task_tool.validate_args({"due_date": "tomorrow"})
        assert len(errs) > 0

        # String too long or wrong type
        errs = create_task_tool.validate_args({"title": 12345})
        assert len(errs) > 0

        # Ring phone validation
        ring_tool = default_registry.get("ring_phone")
        assert ring_tool.validate_args({}) == []
        assert ring_tool.validate_args({"target_device": "my phone"}) == []

        # Send note validation
        note_tool = default_registry.get("send_note")
        assert note_tool.validate_args({"text": "Hello"}) == []
        errs = note_tool.validate_args({})
        assert len(errs) > 0

    def test_openai_tool_conversion(self):
        openai_tools = default_registry.openai_tools_list()
        assert len(openai_tools) >= 11
        for t in openai_tools:
            assert t["type"] == "function"
            assert "name" in t["function"]
            assert "description" in t["function"]
            assert "parameters" in t["function"]


class TestC1ActiveTaskMemory:
    def setup_method(self):
        _active_task_memory.clear()

    def test_record_and_retrieve_memory(self):
        user_id = 999
        record_active_task_action(user_id, "search_web", {"query": "weather"}, {"success": True, "message": "Done"})
        record_active_task_action(user_id, "open_url", {"url": "https://example.com"}, {"success": True})

        mem = get_active_task_memory(user_id)
        assert len(mem) == 2
        assert mem[0]["tool"] == "search_web"
        assert mem[1]["tool"] == "open_url"

    def test_memory_window_expiration(self):
        user_id = 888
        record_active_task_action(user_id, "search_web", {"query": "old"}, {"success": True})
        # Artificially set timestamp to 31 minutes ago
        _active_task_memory[user_id][0]["timestamp"] = time.time() - 1900

        # Retrieve should prune expired entries
        mem = get_active_task_memory(user_id)
        assert len(mem) == 0


class TestC1StepLog:
    def test_step_description_formatting(self):
        assert "Created task proposal: 'Buy milk'" in format_step_description("create_task", {"title": "Buy milk"}, {})
        assert "Searched the web for 'Python'" in format_step_description("search_web", {"query": "Python"}, {})
        assert "Sent note to phone: 'Code 123'" in format_step_description("send_note", {"target_device": "phone", "text": "Code 123"}, {})
        assert "Triggered ring on laptop" in format_step_description("ring_phone", {"target_device": "laptop"}, {})
        assert "Opened https://google.com" in format_step_description("open_url", {"url": "https://google.com"}, {})


@pytest.mark.asyncio
class TestC1AgentLoop:
    async def test_agent_loop_emergency_stop(self):
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.is_emergency_stopped.return_value = True

        result = await run_agent_loop(
            user_id=1,
            user_message="open youtube",
            chat_history=[],
            remembered_facts=[],
            user_devices=[],
            db_module=mock_db,
        )

        assert result.error == "emergency_stopped"
        assert "Emergency stop" in result.reply

    async def test_agent_loop_mock_llm_tool_call(self):
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.is_emergency_stopped.return_value = False
        mock_db.set_pending_proposal.return_value = 123
        mock_db.get_setting.return_value = "alarm_tone"

        # Mock LLM calling create_task then returning final text
        responses = [
            # First turn: call create_task tool
            {
                "success": True,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "tc_1",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": '{"title": "Call dentist", "due_date": "tomorrow at 10am"}'
                            }
                        }
                    ]
                },
                "finish_reason": "tool_calls",
            },
            # Second turn: final assistant message
            {
                "success": True,
                "message": {
                    "role": "assistant",
                    "content": "I've noted that down for you! Call dentist tomorrow at 10am 🌸",
                },
                "finish_reason": "stop",
            }
        ]

        with patch("app.agent_loop._call_llm_with_tools", side_effect=responses), \
             patch("app.agent_loop.get_llm_credentials", return_value={"provider": "groq", "api_key": "test", "endpoint": "https://test", "model": "test"}):
            result = await run_agent_loop(
                user_id=1,
                user_message="Remind me to call dentist tomorrow at 10am",
                chat_history=[],
                remembered_facts=[],
                user_devices=[],
                db_module=mock_db,
            )

            assert "Call dentist" in result.reply
            assert len(result.step_log) > 0
            assert "Created task proposal" in result.step_log[0]
            assert result.proposal is not None
            assert result.proposal["title"] == "Call dentist"
