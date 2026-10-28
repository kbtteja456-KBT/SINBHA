"""
SINBHA Agent Tool Registry (Step C1)

Defines tools with JSON schemas and risk levels that the AI agent can call.
Each tool wraps an existing backend capability (tasks, facts, search, devices, relay).

Risk Levels:
  0 = read-only, auto-execute
  1 = safe side-effect, auto-execute
  2 = confirm before executing (shows confirmation card)
  3 = sensitive, always confirm even if device is trusted
  4 = never automatic (reserved)

Security invariants:
  - No tool may build shell commands from user text
  - Every argument is validated against its JSON schema before execution
  - Tool results are sanitized before returning to the LLM
  - Web content is untrusted; tools triggered by web content are blocked
"""

import re
import time
import json
import jsonschema
from typing import Any, Callable, Dict, List, Optional


# --------------- Tool Definition ---------------

class Tool:
    """A single tool the agent can call."""

    __slots__ = (
        "name", "description", "parameters", "risk_level",
        "handler", "confirmation_template",
    )

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        risk_level: int,
        handler: Callable,
        confirmation_template: str = "",
    ):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema object
        self.risk_level = risk_level  # 0-4
        self.handler = handler        # async (user_id, args, ctx) -> dict
        self.confirmation_template = confirmation_template

    def validate_args(self, args: dict) -> List[str]:
        """Validate arguments against the JSON schema. Returns list of errors."""
        errors = []
        try:
            jsonschema.validate(instance=args, schema=self.parameters)
        except jsonschema.ValidationError as e:
            errors.append(str(e.message))
        except jsonschema.SchemaError as e:
            errors.append(f"Schema error: {e.message}")
        return errors

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI-compatible tool definition for the LLM API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


# --------------- Tool Registry ---------------

class ToolRegistry:
    """Central registry of all available tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def openai_tools_list(self) -> List[dict]:
        """Returns all tools in OpenAI function-calling format."""
        return [t.to_openai_tool() for t in self._tools.values()]


# --------------- Argument Sanitizers ---------------

_DANGEROUS_SHELL_CHARS = re.compile(r'[;&|`$(){}<>!\n\r]')

def sanitize_text_arg(value: str, max_length: int = 500) -> str:
    """Clamp length, strip control characters. Does NOT allow shell metacharacters in sensitive contexts."""
    if not isinstance(value, str):
        return ""
    return value[:max_length].strip()

def sanitize_app_name(value: str) -> str:
    """Only alphanumeric, spaces, dots, hyphens allowed in app names."""
    clean = re.sub(r'[^a-zA-Z0-9 .\-]', '', str(value)).strip().lower()
    return clean[:80]

def sanitize_url(value: str) -> Optional[str]:
    """Only allow http/https URLs. Block javascript: and data: schemes."""
    value = str(value).strip()
    if not value:
        return None
    if not re.match(r'^https?://', value, re.IGNORECASE):
        # Try to auto-prefix
        if re.match(r'^[a-zA-Z0-9][\w.-]+\.[a-zA-Z]{2,}', value):
            value = f"https://{value}"
        else:
            return None
    # Block dangerous schemes embedded
    if re.search(r'javascript:|data:|vbscript:', value, re.IGNORECASE):
        return None
    return value[:2000]


# ============================================================
#  TOOL HANDLER FUNCTIONS
#  Each handler signature: async (user_id, args, ctx) -> dict
#  ctx contains: db, relay_manager, search module, user timezone, etc.
# ============================================================

async def handle_create_task(user_id: int, args: dict, ctx: dict) -> dict:
    """Creates a task proposal (requires user confirmation via the existing proposal flow)."""
    db = ctx["db"]
    title = sanitize_text_arg(args.get("title", ""), 200)
    due_date = args.get("due_date")
    notes = args.get("notes")

    if not title or len(title) < 3:
        return {"success": False, "error": "Task title must be at least 3 characters."}

    # Parse the due date using existing parser
    from app.ai_brain import parse_relative_datetime
    user_tz = ctx.get("user_timezone", "UTC")
    dt_res = parse_relative_datetime(due_date or "", user_timezone=user_tz)

    real_due = dt_res.get("due_date")
    due_time = dt_res.get("due_time")
    due_datetime = dt_res.get("due_datetime")
    suggested_rems = dt_res.get("suggested_reminders", [])

    prop_id = db.set_pending_proposal(
        user_id=user_id,
        title=title,
        due_date=real_due,
        notes=notes,
        due_time=due_time,
        due_datetime=due_datetime,
        suggested_reminders=suggested_rems,
    )

    return {
        "success": True,
        "proposal_id": prop_id,
        "title": title,
        "due_date": real_due,
        "due_time": due_time,
        "display_due": dt_res.get("display"),
        "is_ambiguous": dt_res.get("is_ambiguous", False),
        "ambiguous_options": dt_res.get("ambiguous_options", []),
        "suggested_reminders": suggested_rems,
        "needs_user_confirmation": True,
        "message": f"Task proposal created: '{title}'. Waiting for user confirmation.",
    }


async def handle_complete_task(user_id: int, args: dict, ctx: dict) -> dict:
    """Marks a task as completed after finding the best match."""
    db = ctx["db"]
    query = sanitize_text_arg(args.get("query", ""), 200)
    task_id = args.get("task_id")

    all_tasks = db.get_all_tasks(user_id)
    pending = [t for t in all_tasks if t.get("status") == "pending"]

    if task_id:
        target = next((t for t in pending if t["id"] == task_id), None)
        if not target:
            return {"success": False, "error": f"No pending task with ID {task_id} found."}
    elif query:
        from app.ai_brain import find_matching_tasks
        matches = find_matching_tasks(query, pending)
        if len(matches) == 0:
            return {"success": False, "error": f"No pending task matching '{query}' found.", "pending_tasks": [t["title"] for t in pending[:5]]}
        if len(matches) > 1:
            return {"success": False, "error": "Multiple tasks match. Please be more specific.", "candidates": [{"id": t["id"], "title": t["title"]} for t in matches]}
        target = matches[0]
    else:
        if len(pending) == 1:
            target = pending[0]
        else:
            return {"success": False, "error": "Please specify which task to complete.", "pending_tasks": [{"id": t["id"], "title": t["title"]} for t in pending[:5]]}

    db.set_pending_task_action(user_id, "task_complete", target["id"], target["title"])
    return {
        "success": True,
        "task_id": target["id"],
        "task_title": target["title"],
        "needs_user_confirmation": True,
        "message": f"Ready to mark '{target['title']}' as completed. Waiting for user confirmation.",
    }


async def handle_delete_task(user_id: int, args: dict, ctx: dict) -> dict:
    """Deletes a task after finding the best match."""
    db = ctx["db"]
    query = sanitize_text_arg(args.get("query", ""), 200)
    task_id = args.get("task_id")

    all_tasks = db.get_all_tasks(user_id)

    if task_id:
        target = next((t for t in all_tasks if t["id"] == task_id), None)
        if not target:
            return {"success": False, "error": f"No task with ID {task_id} found."}
    elif query:
        from app.ai_brain import find_matching_tasks
        matches = find_matching_tasks(query, all_tasks)
        if len(matches) == 0:
            return {"success": False, "error": f"No task matching '{query}' found."}
        if len(matches) > 1:
            return {"success": False, "error": "Multiple tasks match. Please be more specific.", "candidates": [{"id": t["id"], "title": t["title"]} for t in matches]}
        target = matches[0]
    else:
        return {"success": False, "error": "Please specify which task to delete."}

    db.set_pending_task_action(user_id, "task_delete", target["id"], target["title"])
    return {
        "success": True,
        "task_id": target["id"],
        "task_title": target["title"],
        "needs_user_confirmation": True,
        "message": f"Ready to delete '{target['title']}'. Waiting for user confirmation.",
    }


async def handle_remember_fact(user_id: int, args: dict, ctx: dict) -> dict:
    """Saves or updates a fact in the user's memory."""
    db = ctx["db"]
    fact_text = sanitize_text_arg(args.get("fact", ""), 300)
    category = sanitize_text_arg(args.get("category", "general"), 50)

    if not fact_text or len(fact_text) < 3:
        return {"success": False, "error": "Fact text must be at least 3 characters."}

    result = db.update_or_add_fact(user_id, fact_text, category)
    return {
        "success": True,
        "action": result.get("action", "none"),
        "fact_id": result.get("fact_id"),
        "fact": result.get("fact", fact_text),
        "message": f"Remembered: '{fact_text}'",
    }


async def handle_forget_fact(user_id: int, args: dict, ctx: dict) -> dict:
    """Finds and prepares to forget a fact from the user's memory."""
    db = ctx["db"]
    from app.ai_brain import find_target_fact_to_forget

    query = sanitize_text_arg(args.get("query", ""), 200)
    facts = db.get_all_facts(user_id)

    if not facts:
        return {"success": False, "error": "No facts saved in memory to forget."}

    target = find_target_fact_to_forget(query or "forget that", facts)
    if not target:
        return {"success": False, "error": "Could not find matching fact to forget."}

    db.set_pending_action(user_id, "forget_fact", target_id=target["id"], target_text=target["fact"])
    return {
        "success": True,
        "fact_id": target["id"],
        "fact_text": target["fact"],
        "needs_user_confirmation": True,
        "message": f"Ready to forget: '{target['fact']}'. Waiting for user confirmation.",
    }


async def handle_search_web(user_id: int, args: dict, ctx: dict) -> dict:
    """Performs a web search using Tavily."""
    query = sanitize_text_arg(args.get("query", ""), 300)
    if not query:
        return {"success": False, "error": "Search query is required."}

    db = ctx["db"]
    web_search_setting = db.get_setting(user_id, "web_search_enabled", "true")
    if web_search_setting != "true":
        return {"success": False, "error": "Web search is disabled in your settings."}

    from app.search import execute_web_search
    user_facts = db.get_all_facts(user_id)
    user_email = ctx.get("user_email", "")

    search_res = await execute_web_search(
        user_id=user_id,
        raw_query=query,
        direct_url=None,
        user_facts=user_facts,
        user_email=user_email,
    )

    if search_res.limit_reached:
        return {"success": False, "error": search_res.limit_message or "Search limit reached."}

    if search_res.searched:
        return {
            "success": True,
            "context": search_res.context_text[:3000],  # Truncate for LLM context
            "sources": search_res.sources[:5],
            "cached": search_res.cached,
        }

    return {"success": False, "error": search_res.error or "Search returned no results."}


async def handle_fetch_page(user_id: int, args: dict, ctx: dict) -> dict:
    """Fetches readable text from a single webpage URL."""
    url = sanitize_url(args.get("url", ""))
    if not url:
        return {"success": False, "error": "Valid URL is required."}

    db = ctx["db"]
    web_search_setting = db.get_setting(user_id, "web_search_enabled", "true")
    if web_search_setting != "true":
        return {"success": False, "error": "Web search/fetch is disabled in your settings."}

    from app.search import execute_web_search
    user_facts = db.get_all_facts(user_id)
    user_email = ctx.get("user_email", "")

    search_res = await execute_web_search(
        user_id=user_id,
        raw_query="",
        direct_url=url,
        user_facts=user_facts,
        user_email=user_email,
    )

    if search_res.limit_reached:
        return {"success": False, "error": search_res.limit_message or "Fetch limit reached."}

    if search_res.searched:
        return {
            "success": True,
            "context": search_res.context_text[:3000],
            "sources": search_res.sources[:3],
        }

    return {"success": False, "error": "Could not fetch page content."}


async def handle_list_devices(user_id: int, args: dict, ctx: dict) -> dict:
    """Lists all user devices with online status and battery telemetry."""
    db = ctx["db"]
    relay = ctx["relay_manager"]

    devs = db.get_user_devices(user_id)
    if not devs:
        return {"success": True, "devices": [], "message": "No devices connected yet."}

    result = []
    for d in devs:
        is_online = relay.is_device_connected(user_id, d.get("device_id"))
        tel = relay.get_device_telemetry(user_id, d.get("device_id"))
        result.append({
            "device_id": d.get("device_id"),
            "name": d.get("name"),
            "platform": d.get("platform"),
            "status": d.get("status"),
            "is_online": is_online,
            "battery": tel.get("battery") if tel else None,
            "is_charging": tel.get("is_charging") if tel else None,
        })

    return {"success": True, "devices": result, "count": len(result)}


async def handle_send_note(user_id: int, args: dict, ctx: dict) -> dict:
    """Sends a note to a target device."""
    db = ctx["db"]
    relay = ctx["relay_manager"]
    note_text = sanitize_text_arg(args.get("text", ""), 500)
    target_platform = sanitize_text_arg(args.get("target_device", "phone"), 20).lower()

    if not note_text:
        return {"success": False, "error": "Note text is required."}

    devs = db.get_user_devices(user_id)
    trusted = [d for d in devs if d.get("status") == "trusted"]
    if not trusted:
        return {"success": False, "error": "No trusted devices paired. Please pair a device first."}

    target_dev = _resolve_target_device(trusted, target_platform, relay, user_id)
    if not target_dev:
        return {"success": False, "error": f"No trusted {target_platform} device found."}

    cmd_id = f"cmd_ai_{int(time.time() * 1000)}"
    cmd_data = {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"],
        "target_device": target_dev["device_id"],
        "type": "send_note",
        "payload": {"text": note_text, "source": "ai_assistant"},
        "created_at": time.time(),
        "expiry": 60,
    }
    relay_res = await relay.relay_command(user_id, cmd_data)

    return {
        "success": relay_res.get("success", False),
        "target_device": target_dev.get("name"),
        "message": f"Note sent to {target_dev.get('name')}.",
    }


async def handle_ring_phone(user_id: int, args: dict, ctx: dict) -> dict:
    """Rings the user's phone or laptop to help find it."""
    db = ctx["db"]
    relay = ctx["relay_manager"]
    target_platform = sanitize_text_arg(args.get("target_device", "phone"), 20).lower()

    devs = db.get_user_devices(user_id)
    trusted = [d for d in devs if d.get("status") == "trusted"]
    if not trusted:
        return {"success": False, "error": "No trusted devices paired."}

    target_dev = _resolve_target_device(trusted, target_platform, relay, user_id)
    if not target_dev:
        return {"success": False, "error": f"No trusted {target_platform} device found."}

    cmd_id = f"cmd_ai_{int(time.time() * 1000)}"
    cmd_data = {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"],
        "target_device": target_dev["device_id"],
        "type": "ring_phone",
        "payload": {"source": "ai_assistant"},
        "created_at": time.time(),
        "expiry": 60,
    }
    relay_res = await relay.relay_command(user_id, cmd_data)

    return {
        "success": relay_res.get("success", False),
        "target_device": target_dev.get("name"),
        "message": f"Ringing {target_dev.get('name')}!",
    }


async def handle_open_url(user_id: int, args: dict, ctx: dict) -> dict:
    """Opens a URL on the user's device browser."""
    db = ctx["db"]
    relay = ctx["relay_manager"]
    url = sanitize_url(args.get("url", ""))
    target_platform = sanitize_text_arg(args.get("target_device", "laptop"), 20).lower()

    if not url:
        return {"success": False, "error": "Valid URL is required."}

    devs = db.get_user_devices(user_id)
    trusted = [d for d in devs if d.get("status") == "trusted"]
    if not trusted:
        return {"success": False, "error": "No trusted devices paired."}

    target_dev = _resolve_target_device(trusted, target_platform, relay, user_id)
    if not target_dev:
        return {"success": False, "error": f"No trusted {target_platform} device found."}

    is_online = relay.is_device_connected(user_id, target_dev["device_id"])
    cmd_id = f"cmd_app_{int(time.time() * 1000)}"
    await relay.relay_command(user_id, {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"],
        "target_device": target_dev["device_id"],
        "type": "open_app",
        "payload": {"app": "chrome", "url": url},
        "created_at": time.time(),
        "expiry": 86400,
    })

    status_note = "opened" if is_online else "queued (device offline)"
    return {
        "success": True,
        "target_device": target_dev.get("name"),
        "url": url,
        "message": f"URL {status_note} on {target_dev.get('name')}.",
    }


# --------------- Device Resolution Helper ---------------

_PHONE_PLATFORMS = ("android", "mobile", "ios")
_LAPTOP_PLATFORMS = ("windows", "desktop", "laptop")

def _resolve_target_device(trusted: list, target_hint: str, relay, user_id: int) -> Optional[dict]:
    """Resolves the best matching trusted device from a platform hint."""
    if not trusted:
        return None

    want_phone = any(k in target_hint for k in ("phone", "mobile", "android", "cell"))
    want_laptop = any(k in target_hint for k in ("laptop", "pc", "desktop", "windows", "computer"))

    if want_laptop:
        for d in trusted:
            if d.get("platform", "").lower() in _LAPTOP_PLATFORMS:
                return d
    elif want_phone:
        for d in trusted:
            if d.get("platform", "").lower() in _PHONE_PLATFORMS:
                return d

    # Default: last device (usually phone if >1 device)
    return trusted[-1] if len(trusted) > 1 else trusted[0]


# ============================================================
#  JSON SCHEMAS FOR EACH TOOL
# ============================================================

_SCHEMA_CREATE_TASK = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Clear, concise task title", "minLength": 3, "maxLength": 200},
        "due_date": {"type": ["string", "null"], "description": "When the task is due. Natural language like 'tomorrow at 8am', 'in 30 minutes', 'Friday at 5pm', or null if no deadline."},
        "notes": {"type": ["string", "null"], "description": "Optional notes for the task", "maxLength": 500},
    },
    "required": ["title"],
    "additionalProperties": False,
}

_SCHEMA_COMPLETE_TASK = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Name or keywords of the task to complete", "maxLength": 200},
        "task_id": {"type": ["integer", "null"], "description": "Exact task ID if known"},
    },
    "additionalProperties": False,
}

_SCHEMA_DELETE_TASK = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Name or keywords of the task to delete", "maxLength": 200},
        "task_id": {"type": ["integer", "null"], "description": "Exact task ID if known"},
    },
    "additionalProperties": False,
}

_SCHEMA_REMEMBER_FACT = {
    "type": "object",
    "properties": {
        "fact": {"type": "string", "description": "The fact to remember about the user", "minLength": 3, "maxLength": 300},
        "category": {"type": "string", "description": "Category: general, preference, personal, etc.", "maxLength": 50, "default": "general"},
    },
    "required": ["fact"],
    "additionalProperties": False,
}

_SCHEMA_FORGET_FACT = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "What to forget — keywords or description of the fact", "maxLength": 200},
    },
    "required": ["query"],
    "additionalProperties": False,
}

_SCHEMA_SEARCH_WEB = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query", "minLength": 2, "maxLength": 300},
    },
    "required": ["query"],
    "additionalProperties": False,
}

_SCHEMA_FETCH_PAGE = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to fetch", "maxLength": 2000},
    },
    "required": ["url"],
    "additionalProperties": False,
}

_SCHEMA_LIST_DEVICES = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_SCHEMA_SEND_NOTE = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "The note text to send", "minLength": 1, "maxLength": 500},
        "target_device": {"type": "string", "description": "Target device: 'phone', 'laptop', or device name", "maxLength": 50, "default": "phone"},
    },
    "required": ["text"],
    "additionalProperties": False,
}

_SCHEMA_RING_PHONE = {
    "type": "object",
    "properties": {
        "target_device": {"type": "string", "description": "Which device to ring: 'phone' or 'laptop'", "maxLength": 50, "default": "phone"},
    },
    "additionalProperties": False,
}

_SCHEMA_OPEN_URL = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to open", "maxLength": 2000},
        "target_device": {"type": "string", "description": "Where to open: 'laptop' or 'phone'", "maxLength": 50, "default": "laptop"},
    },
    "required": ["url"],
    "additionalProperties": False,
}


# ============================================================
#  BUILD THE DEFAULT REGISTRY
# ============================================================

def build_default_registry() -> ToolRegistry:
    """Constructs and returns the standard SINBHA tool registry."""
    registry = ToolRegistry()

    registry.register(Tool(
        name="create_task",
        description="Create a new task or reminder for the user. Use when they mention an assignment, deadline, to-do, or ask to be reminded of something.",
        parameters=_SCHEMA_CREATE_TASK,
        risk_level=1,
        handler=handle_create_task,
        confirmation_template="Create task: '{title}'",
    ))

    registry.register(Tool(
        name="complete_task",
        description="Mark a task as completed. Use when the user says they finished or completed a task.",
        parameters=_SCHEMA_COMPLETE_TASK,
        risk_level=2,
        handler=handle_complete_task,
        confirmation_template="Mark '{task_title}' as done?",
    ))

    registry.register(Tool(
        name="delete_task",
        description="Delete/remove a task from the user's list. Use when they ask to delete or remove a task.",
        parameters=_SCHEMA_DELETE_TASK,
        risk_level=3,
        handler=handle_delete_task,
        confirmation_template="Delete '{task_title}'?",
    ))

    registry.register(Tool(
        name="remember_fact",
        description="Save a personal fact about the user to memory (name, preferences, hobbies, routines, etc). Use when the user shares personal information worth remembering.",
        parameters=_SCHEMA_REMEMBER_FACT,
        risk_level=1,
        handler=handle_remember_fact,
    ))

    registry.register(Tool(
        name="forget_fact",
        description="Forget/delete a saved fact from the user's memory. Use when they ask to forget something.",
        parameters=_SCHEMA_FORGET_FACT,
        risk_level=2,
        handler=handle_forget_fact,
        confirmation_template="Forget: '{fact_text}'?",
    ))

    registry.register(Tool(
        name="search_web",
        description="Search the web for real-time information, news, prices, facts, or anything the user needs. Use when the user asks a question that needs current or factual information you don't have.",
        parameters=_SCHEMA_SEARCH_WEB,
        risk_level=0,
        handler=handle_search_web,
    ))

    registry.register(Tool(
        name="fetch_page",
        description="Fetch and read the text content of a specific webpage URL. Use when the user shares a link and wants to know what it contains.",
        parameters=_SCHEMA_FETCH_PAGE,
        risk_level=0,
        handler=handle_fetch_page,
    ))

    registry.register(Tool(
        name="list_devices",
        description="List all the user's connected companion devices with their online status and battery levels. Use when they ask about their devices, which ones are connected, or battery status.",
        parameters=_SCHEMA_LIST_DEVICES,
        risk_level=0,
        handler=handle_list_devices,
    ))

    registry.register(Tool(
        name="send_note",
        description="Send a note/message to the user's phone or laptop. Use when they ask to send or push a note to their other device.",
        parameters=_SCHEMA_SEND_NOTE,
        risk_level=2,
        handler=handle_send_note,
        confirmation_template="Send note to {target_device}: '{text}'?",
    ))

    registry.register(Tool(
        name="ring_phone",
        description="Ring the user's phone or laptop loudly to help them find it. Use when they ask to ring, find, buzz, or ping their device.",
        parameters=_SCHEMA_RING_PHONE,
        risk_level=3,
        handler=handle_ring_phone,
        confirmation_template="Ring {target_device}?",
    ))

    registry.register(Tool(
        name="open_url",
        description="Open a URL in the browser on the user's laptop or phone. Use when they ask to open a website or link on their device.",
        parameters=_SCHEMA_OPEN_URL,
        risk_level=2,
        handler=handle_open_url,
        confirmation_template="Open {url} on {target_device}?",
    ))

    return registry


# Singleton registry instance
default_registry = build_default_registry()
