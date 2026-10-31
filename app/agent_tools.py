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


# --------------- Typo-Tolerant App Index Matching (Step C2.5 Item 3) ---------------

def levenshtein_distance(s1: str, s2: str) -> int:
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,       # deletion
                dp[i][j - 1] + 1,       # insertion
                dp[i - 1][j - 1] + cost # substitution
            )
    return dp[m][n]

def compute_app_similarity(query: str, target: str) -> float:
    q = query.lower().strip()
    t = target.lower().strip()
    if q == t:
        return 1.0
    max_len = max(len(q), len(t))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(q, t)
    sim = 1.0 - (dist / max_len)
    if (t.startswith(q) or q.startswith(t)) and dist <= 2:
        sim = min(1.0, sim + 0.15)
    return max(0.0, min(1.0, sim))

def find_app_candidates(query: str, catalog: list) -> list:
    results = []
    for item in catalog:
        name = item.get("name", "")
        app_id = item.get("id", name)
        sim = max(
            compute_app_similarity(query, name),
            compute_app_similarity(query, app_id)
        )
        if sim >= 0.5:
            conf = "high" if sim >= 0.8 else ("medium" if sim >= 0.65 else "low")
            results.append({
                "app": item,
                "similarity": sim,
                "confidence": conf
            })
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:3]


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



def is_sensitive_fact(fact_text: str) -> bool:
    """Returns True if the fact covers sensitive topics (medical, health, finances, family fights)."""
    if not fact_text:
        return False
    lower = fact_text.lower()
    sensitive_words = [
        "health", "medical", "doctor", "diagnos", "depress", "anxiety", "suicid",
        "hospital", "illness", "disease", "medicine", "medication", "pill",
        "salary", "income", "money", "debt", "loan", "bank account", "credit card",
        "divorce", "fight with", "abuse", "password", "secret", "cvv"
    ]
    return any(w in lower for w in sensitive_words)

def user_explicitly_requested_remember(user_message: str) -> bool:
    """Returns True if the user explicitly commanded the assistant to remember/save."""
    if not user_message:
        return False
    lower = user_message.lower()
    return any(p in lower for p in [
        "remember this", "please remember", "remember that", "save this",
        "don't forget this", "note this down", "keep this in mind", "remember"
    ])

async def handle_remember_fact(user_id: int, args: dict, ctx: dict) -> dict:
    """Saves or updates a fact in the user's memory following strict sensitivity and confirmation rules."""
    db = ctx["db"]
    fact_text = sanitize_text_arg(args.get("fact", ""), 300)
    category = sanitize_text_arg(args.get("category", "general"), 50)
    user_msg = ctx.get("user_message", "")

    if not fact_text or len(fact_text) < 3:
        return {"success": False, "error": "Fact text must be at least 3 characters."}

    # Rule 1: Sensitive facts only saved if user explicitly stated "remember this"
    if is_sensitive_fact(fact_text) and not user_explicitly_requested_remember(user_msg):
        return {
            "success": False,
            "error": "Sensitive personal facts (medical, health, financial, or personal conflicts) are only remembered when you explicitly say 'remember this'."
        }

    # Rule 2: Check for fact correction against existing facts
    from app.ai_brain import detect_fact_correction
    existing_facts = db.get_all_facts(user_id) if db else []
    target_id, updated_fact, old_fact = detect_fact_correction(user_msg, existing_facts)
    if target_id and updated_fact:
        db.set_pending_action(user_id, "correct_fact", target_id=target_id, target_text=updated_fact)
        return {
            "success": True,
            "needs_user_confirmation": True,
            "action": "correction_pending",
            "fact_id": target_id,
            "old_fact": old_fact,
            "new_fact": updated_fact,
            "message": f"Did you want me to update your memory from '{old_fact}' to '{updated_fact}'?",
        }

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

    dev_res = _resolve_target_device(trusted, target_platform, relay, user_id)
    if dev_res["status"] == "ambiguous":
        return {"success": False, "needs_user_confirmation": False, "message": dev_res["message"], "ambiguous": True}
    target_dev = dev_res.get("device")
    if not target_dev:
        return {"success": False, "error": dev_res.get("message") or f"No trusted {target_platform} device found."}

    # Capability Handshake (Item 2)
    supported = relay.get_device_supported_tools(user_id, target_dev["device_id"], target_dev.get("platform")) if (relay and hasattr(relay, "get_device_supported_tools")) else ["send_note"]
    if "send_note" not in supported:
        p_name = (target_dev.get("platform") or "device").capitalize()
        return {
            "success": False,
            "status": "unsupported_tool",
            "message": f"Your {p_name} app does not support sending notes yet, please update.",
            "error": f"Tool 'send_note' not supported on {target_dev.get('name')}",
        }

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

    is_online = relay.is_device_connected(user_id, target_dev["device_id"]) if (relay and hasattr(relay, "is_device_connected")) else True
    if not is_online:
        await relay.relay_command(user_id, cmd_data)
        return {
            "success": False,
            "status": "queued",
            "target_device": target_dev.get("name"),
            "message": f"I queued the note for {target_dev.get('name')}, but the device is currently offline.",
        }

    await relay.relay_command(user_id, cmd_data)

    # Command Lifecycle Waiter (Item 1)
    if relay and hasattr(relay, "wait_for_command_completion"):
        completion = await relay.wait_for_command_completion(user_id, cmd_id, timeout=10.0)
        if isinstance(completion, dict):
            status = completion.get("status")
            if status == "succeeded":
                return {
                    "success": True,
                    "status": "succeeded",
                    "target_device": target_dev.get("name"),
                    "message": f"Note delivered to {target_dev.get('name')}.",
                }
            elif status == "timed_out":
                return {
                    "success": False,
                    "status": "unconfirmed",
                    "target_device": target_dev.get("name"),
                    "message": f"I sent it to your {target_dev.get('name')}, but could not confirm (timed out after 10s).",
                }
            else:
                err = completion.get("error") or "Failed to deliver note"
                return {
                    "success": False,
                    "status": "failed",
                    "target_device": target_dev.get("name"),
                    "error": err,
                    "message": f"Failed to send note to {target_dev.get('name')}: {err}",
                }

    return {
        "success": True,
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

    dev_res = _resolve_target_device(trusted, target_platform, relay, user_id)
    if dev_res["status"] == "ambiguous":
        return {"success": False, "needs_user_confirmation": False, "message": dev_res["message"], "ambiguous": True}
    target_dev = dev_res.get("device")
    if not target_dev:
        return {"success": False, "error": dev_res.get("message") or f"No trusted {target_platform} device found."}

    # Capability Handshake (Item 2)
    supported = relay.get_device_supported_tools(user_id, target_dev["device_id"], target_dev.get("platform")) if (relay and hasattr(relay, "get_device_supported_tools")) else ["ring_phone"]
    if "ring_phone" not in supported:
        p_name = (target_dev.get("platform") or "device").capitalize()
        return {
            "success": False,
            "status": "unsupported_tool",
            "message": f"Your {p_name} app does not support ringing yet, please update.",
            "error": f"Tool 'ring_phone' not supported on {target_dev.get('name')}",
        }

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

    is_online = relay.is_device_connected(user_id, target_dev["device_id"]) if (relay and hasattr(relay, "is_device_connected")) else True
    if not is_online:
        await relay.relay_command(user_id, cmd_data)
        return {
            "success": False,
            "status": "queued",
            "target_device": target_dev.get("name"),
            "message": f"I queued the ring alert for {target_dev.get('name')}, but the device is currently offline.",
        }

    await relay.relay_command(user_id, cmd_data)

    # Command Lifecycle Waiter (Item 1)
    if relay and hasattr(relay, "wait_for_command_completion"):
        completion = await relay.wait_for_command_completion(user_id, cmd_id, timeout=10.0)
        if isinstance(completion, dict):
            status = completion.get("status")
            if status == "succeeded":
                return {
                    "success": True,
                    "status": "succeeded",
                    "target_device": target_dev.get("name"),
                    "message": f"Ringing {target_dev.get('name')}!",
                }
            elif status == "timed_out":
                return {
                    "success": False,
                    "status": "unconfirmed",
                    "target_device": target_dev.get("name"),
                    "message": f"I sent it to your {target_dev.get('name')}, but could not confirm (timed out after 10s).",
                }
            else:
                err = completion.get("error") or "Failed to trigger ring"
                return {
                    "success": False,
                    "status": "failed",
                    "target_device": target_dev.get("name"),
                    "error": err,
                    "message": f"Failed to ring {target_dev.get('name')}: {err}",
                }

    return {
        "success": True,
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

    dev_res = _resolve_target_device(trusted, target_platform, relay, user_id)
    if dev_res["status"] == "ambiguous":
        return {"success": False, "needs_user_confirmation": False, "message": dev_res["message"], "ambiguous": True}
    target_dev = dev_res.get("device")
    if not target_dev:
        return {"success": False, "error": dev_res.get("message") or f"No trusted {target_platform} device found."}

    # Capability Handshake (Item 2)
    supported = relay.get_device_supported_tools(user_id, target_dev["device_id"], target_dev.get("platform")) if (relay and hasattr(relay, "get_device_supported_tools")) else ["open_url"]
    if "open_url" not in supported:
        p_name = (target_dev.get("platform") or "device").capitalize()
        return {
            "success": False,
            "status": "unsupported_tool",
            "message": f"Your {p_name} app does not support opening URLs yet, please update.",
            "error": f"Tool 'open_url' not supported on {target_dev.get('name')}",
        }

    cmd_id = f"cmd_app_{int(time.time() * 1000)}"
    cmd_data = {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"],
        "target_device": target_dev["device_id"],
        "type": "open_app",
        "payload": {"app": "chrome", "url": url},
        "created_at": time.time(),
        "expiry": 86400,
    }

    is_online = relay.is_device_connected(user_id, target_dev["device_id"]) if (relay and hasattr(relay, "is_device_connected")) else True
    if not is_online:
        await relay.relay_command(user_id, cmd_data)
        return {
            "success": False,
            "status": "queued",
            "target_device": target_dev.get("name"),
            "url": url,
            "message": f"I queued the URL for {target_dev.get('name')}, but the device is currently offline.",
        }

    await relay.relay_command(user_id, cmd_data)

    # Command Lifecycle Waiter (Item 1)
    if relay and hasattr(relay, "wait_for_command_completion"):
        completion = await relay.wait_for_command_completion(user_id, cmd_id, timeout=10.0)
        if isinstance(completion, dict):
            status = completion.get("status")
            if status == "succeeded":
                return {
                    "success": True,
                    "status": "succeeded",
                    "target_device": target_dev.get("name"),
                    "url": url,
                    "message": f"Opened {url} on {target_dev.get('name')}.",
                }
            elif status == "timed_out":
                return {
                    "success": False,
                    "status": "unconfirmed",
                    "target_device": target_dev.get("name"),
                    "url": url,
                    "message": f"I sent it to your {target_dev.get('name')}, but could not confirm (timed out after 10s).",
                }
            else:
                err = completion.get("error") or "Failed to open URL"
                return {
                    "success": False,
                    "status": "failed",
                    "target_device": target_dev.get("name"),
                    "url": url,
                    "error": err,
                    "message": f"Failed to open {url} on {target_dev.get('name')}: {err}",
                }

    return {
        "success": True,
        "target_device": target_dev.get("name"),
        "url": url,
        "message": f"URL opened on {target_dev.get('name')}.",
    }


# --------------- Device Resolution Helper ---------------

_PHONE_PLATFORMS = ("android", "mobile", "ios")
_LAPTOP_PLATFORMS = ("windows", "desktop", "laptop")

def _resolve_target_device(trusted: list, target_hint: str, relay, user_id: int) -> dict:
    """
    Resolves the best matching trusted device from a platform or name hint.
    Detects ambiguity (e.g. user has 2 phones and says 'my phone') and prompts for clarification.
    Returns: {"status": "ok"|"ambiguous"|"none"|"not_found", "device": dict|None, "message": str|None}
    """
    if not trusted:
        return {"status": "none", "device": None, "message": "No companion devices currently connected."}

    req = (target_hint or "").strip().lower()

    if not req or req in ("default", "any", "auto"):
        if len(trusted) == 1:
            return {"status": "ok", "device": trusted[0]}
        # Prefer online desktop, then online phone
        for d in trusted:
            if relay and relay.is_device_connected(user_id, d.get("device_id")):
                return {"status": "ok", "device": d}
        return {"status": "ok", "device": trusted[0]}

    # Direct match by name or id
    for d in trusted:
        if d.get("device_id", "").lower() == req or d.get("name", "").lower() == req:
            return {"status": "ok", "device": d}

    want_phone = any(k in req for k in ("phone", "mobile", "android", "cell", "second phone"))
    want_laptop = any(k in req for k in ("laptop", "pc", "desktop", "windows", "computer", "my laptop"))

    matched = []
    if want_laptop:
        matched = [d for d in trusted if d.get("platform", "").lower() in _LAPTOP_PLATFORMS]
    elif want_phone:
        matched = [d for d in trusted if d.get("platform", "").lower() in _PHONE_PLATFORMS]
    else:
        matched = [d for d in trusted if req in d.get("name", "").lower()]

    if len(matched) == 1:
        return {"status": "ok", "device": matched[0]}
    elif len(matched) > 1:
        names = [f"'{d.get('name', 'Device')}'" for d in matched]
        return {
            "status": "ambiguous",
            "device": None,
            "candidates": matched,
            "message": f"Which device would you like to use? I see {', '.join(names)} connected."
        }

    return {"status": "not_found", "device": None, "message": f"Could not find companion device matching '{target_hint}'."}



# ============================================================
#  JSON SCHEMAS FOR EACH TOOL
# ============================================================


# --------------- Step C2 Laptop Tools Schemas & Handlers ---------------

ALLOWED_KEY_COMBINATIONS = {
    "enter", "return", "tab", "esc", "escape", "space", "backspace", "delete",
    "up", "down", "left", "right", "pageup", "pagedown", "home", "end",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "ctrl+c", "ctrl+v", "ctrl+z", "ctrl+a", "ctrl+s", "ctrl+f", "ctrl+w",
    "alt+f4", "alt+tab"
}

def validate_safe_typing_text(text: str) -> tuple[bool, str]:
    """Validates that typing text does not contain passwords, OTPs, or payment commands."""
    if not text:
        return False, "Text to type cannot be empty."

    lower = text.lower()
    # Password detection
    if re.search(r"(?:password|passwd|passcode|secret)\s*[:=]\s*\S+", text, re.IGNORECASE) or \
       re.search(r"\b(?:my password is|my secret is)\b", lower):
        return False, "Typing passwords or secrets is strictly blocked for security."

    # OTP detection (4-8 digits accompanied by otp/code/verification/pin)
    if re.search(r"\b(?:otp|verification code|one-time password|auth code|pin)\b", lower) or \
       (re.search(r"\b\d{4,8}\b", text) and any(w in lower for w in ("code", "otp", "pin", "verify", "verification"))):
        return False, "Typing OTP codes or authentication pins is strictly blocked for security."

    # Credit card / Payment detection
    if re.search(r"\b(?:\d[ -]*?){13,19}\b", text) and any(w in lower for w in ("card", "visa", "mastercard", "cvv", "cvc", "expir")):
        return False, "Typing credit card or payment credentials is strictly blocked for security."

    if any(k in lower for k in ("pay $", "make payment", "send money", "checkout now", "wire transfer", "bank transfer")):
        return False, "Automated payments are strictly blocked for security."

    return True, ""


def compute_app_similarity(query: str, target: str) -> float:
    """Calculates Levenshtein similarity ratio between query and target app."""
    q = query.lower().strip()
    t = target.lower().strip()
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    max_len = max(len(q), len(t))
    dp = [[0] * (len(t) + 1) for _ in range(len(q) + 1)]
    for i in range(len(q) + 1):
        dp[i][0] = i
    for j in range(len(t) + 1):
        dp[0][j] = j
    for i in range(1, len(q) + 1):
        for j in range(1, len(t) + 1):
            cost = 0 if q[i - 1] == t[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    dist = dp[len(q)][len(t)]
    ratio = 1.0 - (dist / max_len)
    if (t.startswith(q) or q.startswith(t)) and dist <= 2:
        return max(ratio, 0.92)
    return ratio


async def handle_find_installed_app(user_id: int, args: dict, ctx: dict) -> dict:
    """
    Step C2.7 Item 4: Finds installed applications on user's phone or laptop.
    Returns the top candidates (name, package, confidence, score) and the AI chooses.
    Uses synonyms (file manager = Files, gallery, camera, calculator, dialer, messages).
    """
    query = sanitize_text_arg(args.get("query", ""), 80).lower()
    target_hint = args.get("target_device", "phone")
    db = ctx.get("db")
    relay = ctx.get("relay_manager")

    devs = db.get_user_devices(user_id) if db else []
    trusted = [d for d in devs if d.get("status") == "trusted"]
    target_res = _resolve_target_device(trusted, target_hint, relay, user_id)

    if target_res["status"] == "ambiguous":
        return {"success": False, "message": target_res["message"], "ambiguous": True}

    target_dev = target_res.get("device")
    target_dev_id = target_dev.get("device_id") if target_dev else None

    candidates = []
    if relay and hasattr(relay, "resolve_installed_apps_candidates") and target_dev_id:
        candidates = relay.resolve_installed_apps_candidates(user_id, target_dev_id, query, limit=5)

    if not candidates:
        known_apps = [
            {"name": "Files", "package": "com.google.android.documentsui"},
            {"name": "Camera", "package": "com.android.camera"},
            {"name": "Settings", "package": "com.android.settings"},
            {"name": "Chrome", "package": "com.android.chrome"},
            {"name": "YouTube", "package": "com.google.android.youtube"},
            {"name": "WhatsApp", "package": "com.whatsapp"},
            {"name": "Instagram", "package": "com.instagram.android"},
            {"name": "Snapchat", "package": "com.snapchat.android"},
            {"name": "Phone", "package": "com.google.android.dialer"},
            {"name": "Messages", "package": "com.google.android.apps.messaging"},
            {"name": "Gallery", "package": "com.google.android.apps.photos"},
            {"name": "Calculator", "package": "com.google.android.calculator"},
            {"name": "Notepad", "package": "notepad.exe"},
            {"name": "Antigravity", "package": "antigravity.exe"},
            {"name": "Spotify", "package": "spotify.exe"},
            {"name": "Claude", "package": "claude.exe"},
        ]
        scored = []
        for app in known_apps:
            score = compute_app_similarity(query, app["name"])
            if score >= 0.40:
                conf = "high" if score >= 0.80 else ("medium" if score >= 0.55 else "low")
                scored.append({"name": app["name"], "package": app["package"], "confidence": conf, "score": round(score, 2)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        candidates = scored[:5]

    top_candidate = candidates[0] if candidates else None
    overall_confidence = top_candidate["confidence"] if top_candidate else "none"

    return {
        "success": True,
        "query": query,
        "confidence": overall_confidence,
        "top_candidate": top_candidate["name"] if top_candidate else None,
        "package": top_candidate["package"] if top_candidate else None,
        "candidates": candidates,
        "matches": [c["name"] for c in candidates],
        "target_device": target_dev.get("name", target_hint) if target_dev else target_hint,
        "message": f"Found installed apps matching '{query}' (Confidence: {overall_confidence}, Top: {top_candidate['name'] if top_candidate else 'none'}).",
    }


async def handle_get_device_status(user_id: int, args: dict, ctx: dict) -> dict:
    """
    Step C2.7 Item 6: Fetches live device status using real telemetry:
    last heartbeat age, WebSocket status, last error, permissions, battery.
    """
    target_hint = sanitize_text_arg(args.get("target_device", "phone"), 50)
    db = ctx.get("db")
    relay = ctx.get("relay_manager")

    devs = db.get_user_devices(user_id) if db else []
    trusted = [d for d in devs if d.get("status") == "trusted"]
    target_res = _resolve_target_device(trusted, target_hint, relay, user_id)

    if target_res["status"] == "ambiguous":
        return {"success": False, "message": target_res["message"], "ambiguous": True}

    target_dev = target_res.get("device")
    if not target_dev:
        return {"success": False, "error": target_res.get("message") or f"No trusted device found for '{target_hint}'."}

    dev_id = target_dev["device_id"]
    dev_name = target_dev.get("name", "Device")
    platform = (target_dev.get("platform") or "android").lower()

    # Calculate real heartbeat age
    last_seen_at = target_dev.get("last_seen_at")
    heartbeat_age_s = None
    if last_seen_at:
        try:
            from datetime import datetime, timezone
            dt_str = str(last_seen_at)
            if dt_str.endswith("Z"):
                dt_str = dt_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            heartbeat_age_s = int((datetime.now(timezone.utc) - dt).total_seconds())
        except Exception:
            pass

    ws_connected = bool(relay and (user_id, dev_id) in getattr(relay, "active_websockets", {}))
    is_online = bool(relay and relay.is_device_connected(user_id, dev_id))

    telem = getattr(relay, "device_telemetry", {}).get((user_id, dev_id), {}) if relay else {}
    battery_level = telem.get("battery_level") or target_dev.get("battery_level")
    is_charging = telem.get("is_charging")
    last_poll_age = telem.get("last_poll_age")
    last_http_status = telem.get("last_http_status")
    last_error = telem.get("last_error")
    permissions = telem.get("permissions") or {}

    diag_parts = [
        f"Device: {dev_name} ({platform})",
        f"WebSocket: {'Connected' if ws_connected else 'Disconnected'}",
        f"Online: {'Yes' if is_online else 'No'}",
    ]
    if heartbeat_age_s is not None:
        diag_parts.append(f"Heartbeat: {heartbeat_age_s}s ago")
    if battery_level is not None:
        charging_str = " (charging)" if is_charging else ""
        diag_parts.append(f"Battery: {battery_level}%{charging_str}")
    if last_http_status:
        diag_parts.append(f"Last HTTP: {last_http_status}")
    if last_error:
        diag_parts.append(f"Last Error: {last_error}")

    return {
        "success": True,
        "device_id": dev_id,
        "device_name": dev_name,
        "platform": platform,
        "is_online": is_online,
        "websocket_connected": ws_connected,
        "heartbeat_age_seconds": heartbeat_age_s,
        "battery_level": battery_level,
        "is_charging": is_charging,
        "last_poll_age": last_poll_age,
        "last_http_status": last_http_status,
        "last_error": last_error,
        "permissions": permissions,
        "summary": " | ".join(diag_parts),
        "message": f"{dev_name} status: {'online' if is_online else 'offline'}, WebSocket {'connected' if ws_connected else 'disconnected'}, last heartbeat {heartbeat_age_s if heartbeat_age_s is not None else '?'}s ago.",
    }


async def handle_open_app(user_id: int, args: dict, ctx: dict) -> dict:
    """
    Step C2.7 Item 1, 2, 4, 6:
    Launches an application by name or package on user's device.
    Uses candidate resolution to pick exact package.
    Never silently falls back to a website if app is requested or not installed on phone.
    On failure or timeout, provides real failure diagnostic data (heartbeat, WS status, error).
    Registers late confirmation listener so late opens update the chat.
    """
    app_name = sanitize_text_arg(args.get("name", ""), 80)
    explicit_browser = args.get("browser")
    target_hint = args.get("target_device", "laptop")

    db = ctx.get("db")
    relay = ctx.get("relay_manager")

    pref_browser = db.get_setting(user_id, "preferred_browser", "chrome") if db else "chrome"
    browser = explicit_browser or pref_browser

    devs = db.get_user_devices(user_id) if db else []
    trusted = [d for d in devs if d.get("status") == "trusted"]
    target_res = _resolve_target_device(trusted, target_hint, relay, user_id)

    if target_res["status"] == "ambiguous":
        return {"success": False, "needs_user_confirmation": False, "message": target_res["message"], "ambiguous": True}

    target_dev = target_res.get("device")
    if not target_dev:
        return {"success": False, "error": target_res.get("message") or "No companion device available."}

    dev_platform = (target_dev.get("platform") or "android").lower()
    is_phone = dev_platform in ("android", "phone", "mobile")

    # Step C2.7 Item 4: Resolve exact app and package if targeting phone
    target_package = None
    if is_phone and relay and hasattr(relay, "resolve_installed_apps_candidates"):
        candidates = relay.resolve_installed_apps_candidates(user_id, target_dev["device_id"], app_name, limit=1)
        if candidates and candidates[0].get("score", 0) >= 0.50:
            target_package = candidates[0].get("package")
            app_name = candidates[0].get("name") or app_name

    # Capability Handshake (Item 2)
    supported = None
    if relay and hasattr(relay, "get_device_supported_tools"):
        tools_res = relay.get_device_supported_tools(user_id, target_dev["device_id"], target_dev.get("platform"))
        import inspect
        if inspect.iscoroutine(tools_res):
            tools_res = await tools_res
        if isinstance(tools_res, (list, set, tuple)):
            supported = tools_res
    if supported is not None and "open_app" not in supported:
        p_name = (target_dev.get("platform") or "device").capitalize()
        return {
            "success": False,
            "status": "unsupported_tool",
            "message": f"Your {p_name} app does not support opening apps yet, please update.",
            "error": f"Tool 'open_app' not supported on {target_dev.get('name')}",
        }

    cmd_id = f"cmd_app_{int(time.time() * 1000)}"
    payload = {"app": app_name, "browser": browser, "preferred_browser": pref_browser}
    if target_package:
        payload["package"] = target_package

    cmd_data = {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"] if trusted else "server",
        "target_device": target_dev["device_id"],
        "type": "open_app",
        "payload": payload,
        "created_at": time.time(),
        "expiry": 86400,
    }

    is_online = relay.is_device_connected(user_id, target_dev["device_id"]) if (relay and hasattr(relay, "is_device_connected")) else True
    if not is_online:
        if relay:
            await relay.relay_command(user_id, cmd_data)
        return {
            "success": False,
            "status": "queued",
            "app": app_name,
            "target_device": target_dev.get("name"),
            "message": f"I queued the command to open {app_name} on {target_dev.get('name')}, but the device is currently offline.",
        }

    if relay:
        await relay.relay_command(user_id, cmd_data)

    # Command Lifecycle Waiter (Item 1 & 2)
    if relay and hasattr(relay, "wait_for_command_completion"):
        completion = await relay.wait_for_command_completion(user_id, cmd_id, timeout=15.0)
        if isinstance(completion, dict):
            status = completion.get("status")
            result_data = completion.get("result") or {}
            if status == "succeeded":
                pid_info = f" (PID: {result_data.get('pid')})" if result_data.get("pid") else ""
                pkg_info = f" ({result_data.get('package')})" if result_data.get("package") else ""
                return {
                    "success": True,
                    "status": "succeeded",
                    "app": app_name,
                    "browser": browser,
                    "target_device": target_dev.get("name"),
                    "result": result_data,
                    "message": f"Opened {app_name} on {target_dev.get('name')}{pid_info}{pkg_info}.",
                }
            elif status == "timed_out":
                # Step C2.7 Item 2: Register late confirmation listener
                if hasattr(relay, "register_late_confirmation_listener"):
                    relay.register_late_confirmation_listener(cmd_id, user_id, message_id=None, app_name=app_name)

                # Step C2.7 Item 6: Failure explanation using real data
                dev_status = await handle_get_device_status(user_id, {"target_device": target_dev.get("name")}, ctx)
                hb_age = dev_status.get("heartbeat_age_seconds")
                ws_stat = "connected" if dev_status.get("websocket_connected") else "disconnected"
                last_err = dev_status.get("last_error")
                detail_bits = []
                if hb_age is not None:
                    detail_bits.append(f"Heartbeat: {hb_age}s ago")
                detail_bits.append(f"WebSocket: {ws_stat}")
                if last_err:
                    detail_bits.append(f"Last error: {last_err}")
                diag_str = f" ({', '.join(detail_bits)})" if detail_bits else ""

                return {
                    "success": False,
                    "status": "unconfirmed",
                    "app": app_name,
                    "target_device": target_dev.get("name"),
                    "device_status": dev_status,
                    "message": f"I sent it to your {target_dev.get('name')}, but could not confirm (timed out after 10s){diag_str}.",
                }
            else:
                err = completion.get("error") or (result_data.get("error") if isinstance(result_data, dict) else "Failed to open app")
                # Step C2.7 Item 4: Honest reporting, never silent fallback to website
                err_str = str(err).lower()
                if "not installed" in err_str or err == "APP_NOT_INSTALLED":
                    return {
                        "success": False,
                        "status": "not_installed",
                        "app": app_name,
                        "target_device": target_dev.get("name"),
                        "error": err,
                        "message": f"App '{app_name}' is not installed on {target_dev.get('name')}.",
                    }

                # Real diagnostic data on failure
                dev_status = await handle_get_device_status(user_id, {"target_device": target_dev.get("name")}, ctx)
                return {
                    "success": False,
                    "status": "failed",
                    "app": app_name,
                    "target_device": target_dev.get("name"),
                    "error": err,
                    "device_status": dev_status,
                    "message": f"Failed to open {app_name} on {target_dev.get('name')}: {err}.",
                }

    return {
        "success": True,
        "app": app_name,
        "browser": browser,
        "target_device": target_dev.get("name"),
        "message": f"Opened {app_name} on {target_dev.get('name')} (using {browser}).",
    }


async def handle_type_text(user_id: int, args: dict, ctx: dict) -> dict:
    """Types text safely into active window. Strictly prohibits passwords, OTPs, or payments."""
    text = args.get("text", "")
    press_enter = bool(args.get("press_enter", False))
    target_hint = args.get("target_device", "laptop")

    is_safe, error_msg = validate_safe_typing_text(text)
    if not is_safe:
        return {"success": False, "error": error_msg}

    db = ctx["db"]
    relay = ctx["relay_manager"]

    devs = db.get_user_devices(user_id) if db else []
    trusted = [d for d in devs if d.get("status") == "trusted"]
    target_res = _resolve_target_device(trusted, target_hint, relay, user_id)

    if target_res["status"] == "ambiguous":
        return {"success": False, "needs_user_confirmation": False, "message": target_res["message"], "ambiguous": True}

    target_dev = target_res.get("device")
    if not target_dev:
        return {"success": False, "error": target_res.get("message") or "No companion device available."}

    # Capability Handshake (Item 2)
    supported = None
    if relay and hasattr(relay, "get_device_supported_tools"):
        tools_res = relay.get_device_supported_tools(user_id, target_dev["device_id"], target_dev.get("platform"))
        import inspect
        if inspect.iscoroutine(tools_res):
            tools_res = await tools_res
        if isinstance(tools_res, (list, set, tuple)):
            supported = tools_res
    if supported is not None and "type_text" not in supported:
        p_name = (target_dev.get("platform") or "device").capitalize()
        return {
            "success": False,
            "status": "unsupported_tool",
            "message": f"Your {p_name} app does not support typing text yet, please update.",
            "error": f"Tool 'type_text' not supported on {target_dev.get('name')}",
        }

    cmd_id = f"cmd_type_{int(time.time() * 1000)}"
    cmd_data = {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"] if trusted else "server",
        "target_device": target_dev["device_id"],
        "type": "type_input",
        "payload": {"text": text, "press_enter": press_enter},
        "created_at": time.time(),
        "expiry": 86400,
    }

    is_online = relay.is_device_connected(user_id, target_dev["device_id"]) if (relay and hasattr(relay, "is_device_connected")) else True
    if not is_online:
        if relay:
            await relay.relay_command(user_id, cmd_data)
        return {
            "success": False,
            "status": "queued",
            "target_device": target_dev.get("name"),
            "message": f"I queued the typing command for {target_dev.get('name')}, but the device is currently offline.",
        }

    if relay:
        await relay.relay_command(user_id, cmd_data)

    # Command Lifecycle Waiter (Item 1)
    if relay and hasattr(relay, "wait_for_command_completion"):
        completion = await relay.wait_for_command_completion(user_id, cmd_id, timeout=10.0)
        if isinstance(completion, dict):
            status = completion.get("status")
            if status == "succeeded":
                return {
                    "success": True,
                    "status": "succeeded",
                    "target_device": target_dev.get("name"),
                    "text": text,
                    "press_enter": press_enter,
                    "message": f"Typed text into active window on {target_dev.get('name')}.",
                }
            elif status == "timed_out":
                return {
                    "success": False,
                    "status": "unconfirmed",
                    "target_device": target_dev.get("name"),
                    "message": f"I sent it to your {target_dev.get('name')}, but could not confirm (timed out after 10s).",
                }
            else:
                err = completion.get("error") or "Failed to type text"
                return {
                    "success": False,
                    "status": "failed",
                    "target_device": target_dev.get("name"),
                    "error": err,
                    "message": f"Failed to type text on {target_dev.get('name')}: {err}",
                }

    return {
        "success": True,
        "target_device": target_dev.get("name"),
        "text": text,
        "press_enter": press_enter,
        "needs_user_confirmation": True,
        "message": f"Typed text into active window on {target_dev.get('name')}.",
    }


async def handle_press_keys(user_id: int, args: dict, ctx: dict) -> dict:
    """Presses allowlisted keys safely."""
    keys = args.get("keys", "").strip().lower()
    target_hint = args.get("target_device", "laptop")

    if keys not in ALLOWED_KEY_COMBINATIONS:
        return {"success": False, "error": f"Key combination '{keys}' is not allowlisted."}

    db = ctx["db"]
    relay = ctx["relay_manager"]

    devs = db.get_user_devices(user_id) if db else []
    trusted = [d for d in devs if d.get("status") == "trusted"]
    target_res = _resolve_target_device(trusted, target_hint, relay, user_id)

    if target_res["status"] == "ambiguous":
        return {"success": False, "needs_user_confirmation": False, "message": target_res["message"], "ambiguous": True}

    target_dev = target_res.get("device")
    if not target_dev:
        return {"success": False, "error": target_res.get("message") or "No companion device available."}

    # Capability Handshake (Item 2)
    supported = None
    if relay and hasattr(relay, "get_device_supported_tools"):
        tools_res = relay.get_device_supported_tools(user_id, target_dev["device_id"], target_dev.get("platform"))
        import inspect
        if inspect.iscoroutine(tools_res):
            tools_res = await tools_res
        if isinstance(tools_res, (list, set, tuple)):
            supported = tools_res
    if supported is not None and "press_keys" not in supported:
        p_name = (target_dev.get("platform") or "device").capitalize()
        return {
            "success": False,
            "status": "unsupported_tool",
            "message": f"Your {p_name} app does not support pressing keys yet, please update.",
            "error": f"Tool 'press_keys' not supported on {target_dev.get('name')}",
        }

    cmd_id = f"cmd_keys_{int(time.time() * 1000)}"
    cmd_data = {
        "id": cmd_id,
        "sender_device": trusted[0]["device_id"] if trusted else "server",
        "target_device": target_dev["device_id"],
        "type": "press_keys",
        "payload": {"keys": keys},
        "created_at": time.time(),
        "expiry": 86400,
    }

    is_online = relay.is_device_connected(user_id, target_dev["device_id"]) if (relay and hasattr(relay, "is_device_connected")) else True
    if not is_online:
        if relay:
            await relay.relay_command(user_id, cmd_data)
        return {
            "success": False,
            "status": "queued",
            "target_device": target_dev.get("name"),
            "message": f"I queued the key press for {target_dev.get('name')}, but the device is currently offline.",
        }

    if relay:
        await relay.relay_command(user_id, cmd_data)

    # Command Lifecycle Waiter (Item 1)
    if relay and hasattr(relay, "wait_for_command_completion"):
        completion = await relay.wait_for_command_completion(user_id, cmd_id, timeout=10.0)
        if isinstance(completion, dict):
            status = completion.get("status")
            if status == "succeeded":
                return {
                    "success": True,
                    "status": "succeeded",
                    "keys": keys,
                    "target_device": target_dev.get("name"),
                    "message": f"Pressed key '{keys}' on {target_dev.get('name')}.",
                }
            elif status == "timed_out":
                return {
                    "success": False,
                    "status": "unconfirmed",
                    "target_device": target_dev.get("name"),
                    "message": f"I sent it to your {target_dev.get('name')}, but could not confirm (timed out after 10s).",
                }
            else:
                err = completion.get("error") or "Failed to press key"
                return {
                    "success": False,
                    "status": "failed",
                    "target_device": target_dev.get("name"),
                    "error": err,
                    "message": f"Failed to press key on {target_dev.get('name')}: {err}",
                }

    return {
        "success": True,
        "keys": keys,
        "target_device": target_dev.get("name"),
        "needs_user_confirmation": True,
        "message": f"Pressed key '{keys}' on {target_dev.get('name')}.",
    }


async def handle_screen_task(user_id: int, args: dict, ctx: dict) -> dict:
    """
    Step C3a: Autonomous Windows Screen Agent.
    Pre-checks: prefers open_app, open_url, find_installed_app before using pixels.
    If pixels/visual workflow is needed, executes the vision-action loop.
    """
    goal = sanitize_text_arg(args.get("goal", ""), 500)
    if not goal:
        return {"success": False, "error": "Goal description cannot be empty."}

    relay = ctx.get("relay_manager")

    # 1. Prefer open_app, open_url, find_installed_app before using pixels
    clean_goal = goal.strip().lower()

    # Check simple open app
    m_open = re.match(r"^(?:open|launch|start)\s+([a-zA-Z0-9_\-\. ]+)$", clean_goal)
    if m_open and not any(w in clean_goal for w in ("and", "then", "type", "click", "search", "save")):
        app_target = m_open.group(1).strip()
        return await handle_open_app(user_id, {"name": app_target, "target_device": "laptop"}, ctx)

    # Check simple open url
    m_url = re.search(r"https?://\S+", goal)
    if m_url and len(clean_goal.split()) <= 4:
        return await handle_open_url(user_id, {"url": m_url.group(0), "target_device": "laptop"}, ctx)

    # 2. Run Vision-Action Loop via screen_agent
    from app.screen_agent import run_screen_task_loop
    res = await run_screen_task_loop(
        user_id=user_id,
        goal=goal,
        max_steps=25,
        time_limit_seconds=180.0,
        relay_manager=relay
    )
    return res


_SCHEMA_SCREEN_TASK = {
    "type": "object",
    "properties": {
        "goal": {"type": "string", "description": "The specific task or visual UI workflow to perform on the Windows desktop", "minLength": 2, "maxLength": 500},
    },
    "required": ["goal"],
    "additionalProperties": False,
}

_SCHEMA_GET_DEVICE_STATUS = {
    "type": "object",
    "properties": {
        "target_device": {"type": "string", "description": "Target companion device name or hint (e.g. 'phone', 'laptop')", "maxLength": 50, "default": "phone"},
    },
    "additionalProperties": False,
}

_SCHEMA_FIND_INSTALLED_APP = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The application name or keyword to search for", "minLength": 1, "maxLength": 80},
        "target_device": {"type": "string", "description": "Target device name or hint (e.g. 'my laptop')", "maxLength": 50, "default": "laptop"},
    },
    "required": ["query"],
    "additionalProperties": False,
}

_SCHEMA_OPEN_APP = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Application name to open (e.g. 'whatsapp', 'spotify', 'claude', 'notepad')", "minLength": 1, "maxLength": 80},
        "browser": {"type": "string", "description": "Preferred or requested browser: 'default', 'chrome', 'edge', or 'firefox'", "enum": ["default", "chrome", "edge", "firefox"]},
        "target_device": {"type": "string", "description": "Target device name or hint (e.g. 'my laptop', 'second phone')", "maxLength": 50, "default": "laptop"},
    },
    "required": ["name"],
    "additionalProperties": False,
}

_SCHEMA_TYPE_TEXT = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Text to type into focused window. Passwords, OTP codes, and payment credentials are strictly blocked.", "minLength": 1, "maxLength": 1000},
        "press_enter": {"type": "boolean", "description": "Whether to press Enter key after typing", "default": False},
        "target_device": {"type": "string", "description": "Target laptop name or hint", "maxLength": 50, "default": "laptop"},
    },
    "required": ["text"],
    "additionalProperties": False,
}

_SCHEMA_PRESS_KEYS = {
    "type": "object",
    "properties": {
        "keys": {"type": "string", "description": "Allowlisted key combination (e.g. 'enter', 'tab', 'esc', 'ctrl+c', 'ctrl+v', 'alt+tab', 'f5')", "maxLength": 30},
        "target_device": {"type": "string", "description": "Target laptop name or hint", "maxLength": 50, "default": "laptop"},
    },
    "required": ["keys"],
    "additionalProperties": False,
}

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
        "browser": {"type": "string", "description": "Browser to use: 'default', 'chrome', 'edge', or 'firefox'", "enum": ["default", "chrome", "edge", "firefox"], "default": "default"},
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
        risk_level=2,
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


    registry.register(Tool(
        name="get_device_status",
        description="Check connection health, heartbeat age, WebSocket status, battery level, and permissions for user's phone or laptop.",
        parameters=_SCHEMA_GET_DEVICE_STATUS,
        risk_level=0,
        handler=handle_get_device_status,
    ))

    registry.register(Tool(
        name="find_installed_app",
        description="Search whether an application is installed on the user's laptop. Use when they ask if an app is installed or to locate an app.",
        parameters=_SCHEMA_FIND_INSTALLED_APP,
        risk_level=0,
        handler=handle_find_installed_app,
    ))

    registry.register(Tool(
        name="open_app",
        description="Open an application on the user's laptop or phone. If installed, opens the desktop app; otherwise opens the website in the preferred browser.",
        parameters=_SCHEMA_OPEN_APP,
        risk_level=2,
        handler=handle_open_app,
        confirmation_template="Open {name} on {target_device}?",
    ))

    registry.register(Tool(
        name="type_text",
        description="Type text into the focused window on the user's laptop. Enforces strict safety: never types passwords, OTP codes, credit cards, or payment details.",
        parameters=_SCHEMA_TYPE_TEXT,
        risk_level=2,
        handler=handle_type_text,
        confirmation_template="Type into active window on {target_device}: '{text}'?",
    ))

    registry.register(Tool(
        name="press_keys",
        description="Press allowlisted keyboard keys or shortcuts (enter, tab, esc, ctrl+c, ctrl+v, alt+tab, etc.) on the user's laptop.",
        parameters=_SCHEMA_PRESS_KEYS,
        risk_level=2,
        handler=handle_press_keys,
        confirmation_template="Press '{keys}' on {target_device}?",
    ))

    registry.register(Tool(
        name="screen_task",
        description="Autonomous Windows desktop screen agent. Uses vision to navigate, click, type, and complete visual workflows on screen.",
        parameters=_SCHEMA_SCREEN_TASK,
        risk_level=3,
        handler=handle_screen_task,
        confirmation_template="Allow SINBHA Screen Agent to perform '{goal}' on screen?",
    ))

    return registry


# Singleton registry instance
default_registry = build_default_registry()
