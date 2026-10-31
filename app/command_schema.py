"""
Shared Command Schema (Step C2.7 Item 3)
Used across the FastAPI server, Android companion, and Windows desktop client.

Defines:
- Standard command types
- Expected payload fields (required & optional)
- Unwrapping logic for legacy 'remote_command' envelopes
- Validation helpers and contract schema definition
"""

from typing import Dict, Any, List, Optional, Tuple

SUPPORTED_COMMAND_TYPES = [
    "open_app",
    "open_url",
    "send_note",
    "ring_phone",
    "sync_tasks",
    "emergency_stop",
    "get_device_status",
]

DEFAULT_PLATFORM_SUPPORTED_TOOLS = {
    "android": [
        "open_app",
        "open_url",
        "send_note",
        "ring_phone",
        "sync_tasks",
        "emergency_stop",
        "get_device_status",
    ],
    "phone": [
        "open_app",
        "open_url",
        "send_note",
        "ring_phone",
        "sync_tasks",
        "emergency_stop",
        "get_device_status",
    ],
    "windows": [
        "open_app",
        "open_url",
        "find_installed_app",
        "type_text",
        "press_keys",
        "send_note",
        "emergency_stop",
        "get_device_status",
    ],
    "laptop": [
        "open_app",
        "open_url",
        "find_installed_app",
        "type_text",
        "press_keys",
        "send_note",
        "emergency_stop",
        "get_device_status",
    ],
    "desktop": [
        "open_app",
        "open_url",
        "find_installed_app",
        "type_text",
        "press_keys",
        "send_note",
        "emergency_stop",
        "get_device_status",
    ],
}

COMMAND_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "open_app": {
        "description": "Launches an application by name or package on the target device.",
        "required_fields": ["app"],
        "optional_fields": ["search_query", "url", "type_text", "browser", "preferred_browser"],
    },
    "open_url": {
        "description": "Opens a web URL in the default or preferred browser.",
        "required_fields": ["url"],
        "optional_fields": ["browser"],
    },
    "send_note": {
        "description": "Displays a high-priority heads-up note or message notification.",
        "required_fields": ["text"],
        "optional_fields": ["title", "sender_name"],
    },
    "ring_phone": {
        "description": "Plays high-priority ringtone on companion phone to help locate it.",
        "required_fields": [],
        "optional_fields": ["sender_name", "duration_seconds"],
    },
    "sync_tasks": {
        "description": "Synchronizes upcoming task alarms and reminders.",
        "required_fields": [],
        "optional_fields": ["tasks", "reminders", "force"],
    },
    "emergency_stop": {
        "description": "Halts all active alarms, sounds, or automated actions immediately.",
        "required_fields": [],
        "optional_fields": ["reason", "sender"],
    },
    "get_device_status": {
        "description": "Fetches live connection, battery, and permission status for device.",
        "required_fields": [],
        "optional_fields": ["target_device", "include_telemetry", "include_installed_apps"],
    },
}

def unwrap_command_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unwraps legacy envelopes where packet['type'] == 'remote_command'
    and the real command is stored under 'command_type'.
    
    Fixes the 'Unsupported command type: remote_command' bug permanently.
    """
    unwrapped = dict(packet)
    raw_type = unwrapped.get("type")
    cmd_type = unwrapped.get("command_type")

    if raw_type == "remote_command" and cmd_type:
        unwrapped["type"] = cmd_type
    elif not raw_type and cmd_type:
        unwrapped["type"] = cmd_type

    # Ensure command_type matches type
    unwrapped["command_type"] = unwrapped.get("type")
    return unwrapped


def validate_command_packet(packet: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Validates that a command conforms to the shared command schema.
    Returns: (is_valid, error_reason, normalized_packet)
    """
    if not isinstance(packet, dict):
        return False, "Command packet must be a JSON object", {}

    norm = unwrap_command_packet(packet)
    cmd_type = norm.get("type")

    if not cmd_type or not isinstance(cmd_type, str):
        return False, "Missing or invalid 'type' field in command packet", norm

    if cmd_type not in SUPPORTED_COMMAND_TYPES:
        return False, f"Unsupported command type: {cmd_type}", norm

    payload = norm.get("payload")
    if payload is None:
        payload = {}
        norm["payload"] = payload

    if not isinstance(payload, dict):
        return False, f"Payload for command '{cmd_type}' must be a JSON object", norm

    # Validate required payload fields
    schema = COMMAND_SCHEMAS.get(cmd_type, {})
    for req in schema.get("required_fields", []):
        val = payload.get(req)
        if val is None or (isinstance(val, str) and not val.strip()):
            return False, f"Command '{cmd_type}' is missing required field '{req}' in payload", norm

    return True, None, norm


def is_command_supported_by_device(
    cmd_type: str,
    device_platform: Optional[str],
    reported_supported_tools: Optional[List[str]] = None,
) -> bool:
    """
    Checks if a target device supports a command type.
    Priority:
    1. Specifically reported capabilities in reported_supported_tools
    2. Platform default tools if capabilities not yet reported
    """
    norm_type = cmd_type.strip().lower()
    if norm_type == "remote_command":
        return True

    if reported_supported_tools and len(reported_supported_tools) > 0:
        return norm_type in [t.lower() for t in reported_supported_tools]

    plat = (device_platform or "android").lower()
    default_tools = DEFAULT_PLATFORM_SUPPORTED_TOOLS.get(plat) or DEFAULT_PLATFORM_SUPPORTED_TOOLS["android"]
    return norm_type in [t.lower() for t in default_tools]
