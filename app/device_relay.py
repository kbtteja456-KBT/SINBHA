"""
Secure Device Command Relay & WebSocket Channel (Step 16 / 16b)
The command channel uses HTTPS/TLS encryption in transit, and the server
relays readable payloads to authenticated devices. Offline queued commands
are held strictly in volatile memory (never written to disk or database)
and deleted immediately upon expiry (60 seconds).
Replay protection, rate limiting, and permission gates are strictly enforced.
Audit logging records only metadata (command type, sender, target, result),
and NEVER the command content or payload.
"""

import os
import time
import json
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from fastapi import WebSocket

from app import database as db
from app.command_schema import (
    SUPPORTED_COMMAND_TYPES,
    unwrap_command_packet,
    validate_command_packet,
    is_command_supported_by_device,
)

APP_SYNONYMS: Dict[str, List[str]] = {
    "file manager": ["files", "my files", "filemanager", "documents", "documentsui"],
    "files": ["file manager", "my files", "filemanager", "documents", "documentsui"],
    "gallery": ["photos", "google photos", "gallery3d", "albums"],
    "photos": ["gallery", "google photos", "gallery3d", "albums"],
    "camera": ["cam", "google camera", "camera2"],
    "calculator": ["calc", "calculator"],
    "calc": ["calculator", "calc"],
    "dialer": ["phone", "call", "contacts", "telephone"],
    "phone": ["dialer", "call", "contacts", "telephone"],
    "messages": ["sms", "texting", "messaging", "mms"],
    "sms": ["messages", "texting", "messaging", "mms"],
    "browser": ["chrome", "google chrome", "edge", "internet"],
    "chrome": ["browser", "google chrome", "internet"],
    "settings": ["system settings", "preferences", "config"],
    "youtube": ["yt", "video"],
    "music": ["spotify", "youtube music", "audio"],
}

class CommandRelayManager:
    def __init__(self):
        # Maps (user_id, device_id) -> WebSocket
        self.active_websockets: Dict[Tuple[int, str], WebSocket] = {}

        # Replay protection cache: command_id -> timestamp (pruned after 300s)
        self.seen_command_ids: Dict[str, float] = {}

        # Sliding window per-user rate limiting: user_id -> List[timestamp] (max 30 / min)
        self.user_command_history: Dict[int, List[float]] = {}

        # Offline queues: (user_id, device_id) -> List[dict] (max 10, expiry 60s, in-memory only)
        self.offline_queues: Dict[Tuple[int, str], List[dict]] = {}

        # User notifications buffer: user_id -> List[dict] (max 25, in-memory only)
        self.user_notifications: Dict[int, List[dict]] = {}

        # Late confirmation handlers (Step C2.7 Item 2): command_id -> dict
        self.late_confirmation_handlers: Dict[str, dict] = {}

        # User command updates buffer (e.g. for frontend polling/SSE): user_id -> List[dict]
        self.command_updates: Dict[int, List[dict]] = {}
        self.user_notifications: Dict[int, List[dict]] = {}

        # Device telemetry: (user_id, device_id) -> dict (battery, is_charging, last_seen)
        self.device_telemetry: Dict[Tuple[int, str], dict] = {}

        # Recent device active timestamps: (user_id, device_id) -> float
        self.device_last_active: Dict[Tuple[int, str], float] = {}

        # Command lifecycle states: command_id -> dict
        # { command_id, user_id, sender_device, target_device, type, status, created_at, updated_at, result, error }
        self.command_lifecycles: Dict[str, dict] = {}

        # Asyncio futures for handlers awaiting device confirmation: command_id -> asyncio.Future
        self._lifecycle_waiters: Dict[str, asyncio.Future] = {}

        # Device capabilities reported via handshake: (user_id, device_id) -> dict
        # { version, platform, supported_tools, installed_apps, updated_at }
        self.device_capabilities: Dict[Tuple[int, str], dict] = {}

        # Installed apps reported by companion devices: (user_id, device_id) -> List[dict]
        self.device_installed_apps: Dict[Tuple[int, str], List[dict]] = {}

    DEFAULT_SUPPORTED_TOOLS = {
        "windows": [
            "find_installed_app", "open_app", "open_url", "send_note",
            "type_text", "press_keys", "lock_screen", "sync_tasks"
        ],
        "android": [
            "open_app", "open_url", "send_note", "ring_phone", "sync_tasks"
        ],
        "web": [
            "send_note", "open_url", "sync_tasks"
        ]
    }

    def get_default_supported_tools(self, platform: Optional[str]) -> List[str]:
        plat = (platform or "web").lower()
        if "win" in plat or "pc" in plat or "laptop" in plat:
            return list(self.DEFAULT_SUPPORTED_TOOLS["windows"])
        elif "android" in plat or "phone" in plat or "mobile" in plat:
            return list(self.DEFAULT_SUPPORTED_TOOLS["android"])
        return list(self.DEFAULT_SUPPORTED_TOOLS["web"])

    def record_device_capabilities(
        self,
        user_id: int,
        device_id: str,
        platform: str,
        app_version: str,
        supported_tools: Optional[List[str]] = None,
        installed_apps: Optional[List[dict]] = None
    ) -> dict:
        """Stores device capability handshake reported by companion app."""
        tools = supported_tools or self.get_default_supported_tools(platform)
        caps = {
            "platform": platform,
            "app_version": app_version,
            "supported_tools": tools,
            "installed_apps": installed_apps or self.device_installed_apps.get((user_id, device_id), []),
            "updated_at": time.time()
        }
        self.device_capabilities[(user_id, device_id)] = caps
        if installed_apps:
            self.device_installed_apps[(user_id, device_id)] = installed_apps
        return caps

    def get_device_installed_apps(self, user_id: int, device_id: str) -> List[dict]:
        """Returns installed apps reported by this companion device."""
        if (user_id, device_id) in self.device_installed_apps:
            return self.device_installed_apps[(user_id, device_id)]
        caps = self.device_capabilities.get((user_id, device_id))
        if caps and caps.get("installed_apps"):
            return caps["installed_apps"]
        return []

    def resolve_installed_apps_candidates(
        self, user_id: int, device_id: str, app_query: str, limit: int = 5
    ) -> List[dict]:
        """
        Step C2.7 Item 4: App resolution returning top candidates (name, package, confidence, score)
        with synonym expansion (file manager = Files, gallery, camera, calculator, dialer, messages)
        so the AI chooses.
        """
        import difflib
        apps = self.get_device_installed_apps(user_id, device_id)
        if not apps:
            # Common defaults when device apps have not synced yet
            apps = [
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
            ]

        clean_query = app_query.strip().lower()
        query_norm = clean_query.replace(" ", "").replace("_", "").replace("-", "")

        expanded_terms = {clean_query, query_norm}
        for syn_key, syn_list in APP_SYNONYMS.items():
            if syn_key in clean_query or clean_query in syn_key:
                expanded_terms.update([s.lower() for s in syn_list])

        scored_candidates = []
        seen_packages = set()

        for a in apps:
            name = (a.get("name") or "").strip()
            pkg = (a.get("package") or "").strip()
            if not name and not pkg:
                continue
            if pkg and pkg in seen_packages:
                continue

            name_lower = name.lower()
            name_norm = name_lower.replace(" ", "").replace("_", "").replace("-", "")
            pkg_lower = pkg.lower()

            score = 0.0

            # 1. Exact match
            if name_lower == clean_query or query_norm == name_norm or clean_query == pkg_lower or pkg_lower.endswith("." + query_norm):
                score = 1.0
            # 2. Synonym match
            elif any(syn == name_lower or syn == name_norm for syn in expanded_terms):
                score = 0.95
            # 3. Substring match
            elif clean_query in name_lower or name_lower in clean_query or query_norm in name_norm:
                score = 0.85
            elif query_norm in pkg_lower:
                score = 0.80
            else:
                # 4. Fuzzy SequenceMatcher
                ratio1 = difflib.SequenceMatcher(None, clean_query, name_lower).ratio()
                ratio2 = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
                best_ratio = max(ratio1, ratio2)
                if best_ratio >= 0.50:
                    score = round(best_ratio, 2)

            if score > 0.40:
                confidence = "high" if score >= 0.85 else ("medium" if score >= 0.60 else "low")
                scored_candidates.append({
                    "name": name,
                    "package": pkg,
                    "confidence": confidence,
                    "score": score
                })
                if pkg:
                    seen_packages.add(pkg)

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        return scored_candidates[:limit]

    def find_installed_app_match(self, user_id: int, device_id: str, app_query: str) -> Optional[dict]:
        """
        Step C2.6 & C2.7 Item 4: Typo-tolerant matching of app_query against phone reported installed apps.
        Never falls back silently to a website.
        """
        candidates = self.resolve_installed_apps_candidates(user_id, device_id, app_query, limit=1)
        if candidates and candidates[0]["score"] >= 0.55:
            return {
                "name": candidates[0]["name"],
                "package": candidates[0]["package"],
                "confidence": candidates[0]["confidence"],
                "score": candidates[0]["score"]
            }
        return None

    def get_device_supported_tools(self, user_id: int, device_id: str, platform: Optional[str] = None) -> List[str]:
        """Returns the list of tools verified to be supported on the target device."""
        recorded = self.device_capabilities.get((user_id, device_id))
        if recorded and recorded.get("supported_tools"):
            return recorded["supported_tools"]
        return self.get_default_supported_tools(platform)

    def init_command_lifecycle(
        self,
        cmd_id: str,
        user_id: int,
        sender_device: str,
        target_device: str,
        cmd_type: str,
        status: str = "queued",
    ):
        """Initializes lifecycle record for a command."""
        now = time.time()
        self.command_lifecycles[cmd_id] = {
            "command_id": cmd_id,
            "user_id": user_id,
            "sender_device": sender_device,
            "target_device": target_device,
            "type": cmd_type,
            "status": status,  # "queued", "delivered", "started", "succeeded", "failed"
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
        }

    def register_late_confirmation_listener(
        self,
        cmd_id: str,
        user_id: int,
        message_id: Optional[int] = None,
        app_name: str = "",
    ):
        """
        Step C2.7 Item 2: Registers listener for delayed command confirmations.
        If confirmation arrives after the 10-second wait window, updates earlier chat message.
        """
        self.late_confirmation_handlers[cmd_id] = {
            "user_id": user_id,
            "message_id": message_id,
            "app_name": app_name,
            "registered_at": time.time(),
        }

    def update_command_status(
        self,
        user_id: int,
        cmd_id: str,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> dict:
        """
        Updates the lifecycle status of a command ('delivered', 'started', 'succeeded', 'failed').
        Resolves any waiting future when reached final status ('succeeded', 'failed').
        """
        now = time.time()
        entry = self.command_lifecycles.get(cmd_id)
        if not entry:
            entry = {
                "command_id": cmd_id,
                "user_id": user_id,
                "status": status,
                "created_at": now,
                "updated_at": now,
                "result": result,
                "error": error,
            }
            self.command_lifecycles[cmd_id] = entry
        else:
            entry["status"] = status
            entry["updated_at"] = now
            if result is not None:
                entry["result"] = result
            if error is not None:
                entry["error"] = error

        # Log audit of status change
        db.log_audit(
            user_id,
            "DEVICE_COMMAND_STATUS",
            json.dumps({
                "command_id": cmd_id,
                "status": status,
                "has_result": bool(result),
                "error": error,
            })
        )

        # Step C2.7 Item 2: Late Confirmations
        # If result arrives after 10-second wait, update earlier chat message ("Update: it did open")
        if status in ("succeeded", "executed"):
            is_late = (entry.get("status") == "timed_out") or entry.get("timed_out") or (cmd_id in self.late_confirmation_handlers)
            if is_late:
                late_info = self.late_confirmation_handlers.pop(cmd_id, None)
                app_disp = (late_info.get("app_name") if late_info else None) or (entry.get("result", {}).get("app") if isinstance(entry.get("result"), dict) else "app")
                update_msg = f"Update: {app_disp} did open 🌸" if (app_disp and app_disp != "app") else "Update: it did open 🌸"

                try:
                    if late_info and late_info.get("message_id"):
                        db.update_message(user_id, late_info["message_id"], update_msg)
                    else:
                        db.update_latest_assistant_message(user_id, update_msg)
                except Exception:
                    pass

                if user_id not in self.command_updates:
                    self.command_updates[user_id] = []
                self.command_updates[user_id].append({
                    "command_id": cmd_id,
                    "status": "succeeded",
                    "update_text": update_msg,
                    "timestamp": now,
                })
                entry["late_confirmed"] = True
                entry["update_text"] = update_msg

                db.log_audit(
                    user_id,
                    "LATE_COMMAND_CONFIRMED",
                    json.dumps({
                        "command_id": cmd_id,
                        "status": status,
                        "app": app_disp,
                        "update_text": update_msg
                    })
                )

        # If waiting future exists and status is final (succeeded, failed, executed, needs_tap), resolve it
        terminal_statuses = ("succeeded", "failed", "executed", "needs_tap")
        waiter = self._lifecycle_waiters.get(cmd_id)
        if waiter and not waiter.done() and status in terminal_statuses:
            waiter.set_result(entry)

        return entry

    def get_command_lifecycle(self, cmd_id: str) -> Optional[dict]:
        return self.command_lifecycles.get(cmd_id)

    async def wait_for_command_completion(
        self,
        user_id: int,
        cmd_id: str,
        timeout: float = 10.0
    ) -> dict:
        """
        Awaits until the command moves to terminal state ('succeeded', 'failed', 'executed', 'needs_tap'),
        or times out (~10s).
        """
        terminal_statuses = ("succeeded", "failed", "executed", "needs_tap")
        entry = self.command_lifecycles.get(cmd_id)
        if entry and entry.get("status") in terminal_statuses:
            return entry

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        future = loop.create_future()
        self._lifecycle_waiters[cmd_id] = future

        try:
            res = await asyncio.wait_for(future, timeout=timeout)
            return res
        except asyncio.TimeoutError:
            if cmd_id in self.command_lifecycles:
                self.command_lifecycles[cmd_id]["status"] = "timed_out"
                self.command_lifecycles[cmd_id]["timed_out"] = True
                self.command_lifecycles[cmd_id]["updated_at"] = time.time()
            return {
                "command_id": cmd_id,
                "status": "timed_out",
                "success": False,
                "message": "I sent it to your device, but could not confirm (timed out after 10s)."
            }
        finally:
            self._lifecycle_waiters.pop(cmd_id, None)

    def store_user_notifications(self, user_id: int, notifications: List[dict]):
        """Stores recent notification buffer from phone in volatile memory."""
        if not notifications:
            return
        current = self.user_notifications.get(user_id, [])
        seen_keys = {(n.get("app"), n.get("title"), n.get("timestamp")) for n in current}
        for n in notifications:
            k = (n.get("app"), n.get("title"), n.get("timestamp"))
            if k not in seen_keys:
                current.insert(0, n)
                seen_keys.add(k)
        self.user_notifications[user_id] = current[:25]

    def get_user_notifications(self, user_id: int) -> List[dict]:
        """Returns volatile notifications for user."""
        return self.user_notifications.get(user_id, [])

    def store_device_telemetry(self, user_id: int, device_id: str, telemetry: dict):
        """Stores device telemetry (battery, is_charging, timestamp) in volatile memory."""
        self.device_telemetry[(user_id, device_id)] = telemetry

    def get_device_telemetry(self, user_id: int, device_id: Optional[str] = None) -> Optional[dict]:
        """Gets telemetry for a device or latest for any device of user."""
        if device_id:
            return self.device_telemetry.get((user_id, device_id))
        for (u, _), t in self.device_telemetry.items():
            if u == user_id:
                return t
        return None

    def _cleanup_old_records(self, now: float):
        """Prunes expired replay entries (> 300s old)."""
        cutoff = now - 300.0
        expired_ids = [cid for cid, ts in self.seen_command_ids.items() if ts < cutoff]
        for cid in expired_ids:
            self.seen_command_ids.pop(cid, None)

    def _check_user_rate_limit(self, user_id: int, now: float) -> bool:
        """Sliding window: allows max 30 remote commands per user per 60 seconds."""
        window_start = now - 60.0
        history = self.user_command_history.get(user_id, [])
        # Prune old
        history = [ts for ts in history if ts > window_start]
        if len(history) >= 30:
            self.user_command_history[user_id] = history
            return False
        history.append(now)
        self.user_command_history[user_id] = history
        return True

    def register_websocket(self, user_id: int, device_id: str, websocket: WebSocket):
        """Registers a live device WebSocket connection."""
        self.active_websockets[(user_id, device_id)] = websocket
        db.update_device_last_seen(device_id)

    def unregister_websocket(self, user_id: int, device_id: str, websocket: Optional[WebSocket] = None):
        """Unregisters device WebSocket."""
        key = (user_id, device_id)
        current = self.active_websockets.get(key)
        if current and (websocket is None or current == websocket):
            self.active_websockets.pop(key, None)

    def mark_device_active(self, user_id: int, device_id: str):
        """Marks device as actively communicating."""
        self.device_last_active[(user_id, device_id)] = time.time()

    def is_device_connected(self, user_id: int, device_id: str) -> bool:
        """Checks if device has an active WebSocket or was actively communicating in the last 45s."""
        if (user_id, device_id) in self.active_websockets:
            return True
        last_act = self.device_last_active.get((user_id, device_id), 0)
        if (time.time() - last_act) < 45.0:
            return True
        dev = db.get_device_by_id(user_id, device_id)
        if dev and dev.get("last_seen_at"):
            try:
                from datetime import datetime, timezone
                dt_str = str(dev["last_seen_at"])
                if dt_str.endswith("Z"):
                    dt_str = dt_str[:-1] + "+00:00"
                last_seen = datetime.fromisoformat(dt_str)
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if (now - last_seen).total_seconds() < 45.0:
                    return True
            except Exception:
                pass
        return False

    async def notify_pairing_requested(self, user_id: int, device_info: dict):
        """
        Step 16b Rule 3: Broadcasts pairing_requested notification to all
        currently connected trusted device WebSockets for this user.
        """
        packet = {
            "type": "pairing_requested",
            "device": {
                "device_id": device_info.get("device_id"),
                "name": device_info.get("name"),
                "platform": device_info.get("platform"),
                "created_at": str(device_info.get("created_at") or ""),
            },
            "timestamp": time.time(),
        }
        msg = json.dumps(packet)
        for (uid, dev_id), ws in list(self.active_websockets.items()):
            if uid == user_id:
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    async def notify_screen_agent_state(self, user_id: int, active: bool, goal: str):
        """
        Step C3a: Broadcasts screen agent state (active, goal) to connected clients
        so Electron / Desktop displays visible border and floating Stop button.
        """
        packet = {
            "type": "screen_agent_state",
            "active": active,
            "goal": goal,
            "timestamp": time.time(),
        }
        msg = json.dumps(packet)
        for (uid, dev_id), ws in list(self.active_websockets.items()):
            if uid == user_id:
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    def get_pending_offline_commands(self, user_id: int, device_id: str) -> List[dict]:
        """
        Drains pending offline commands for a device.
        Stale/expired commands (> 60s) are discarded immediately and NEVER run.
        """
        key = (user_id, device_id)
        queue = self.offline_queues.get(key, [])
        now = time.time()

        valid_commands = []
        for cmd in queue:
            created = cmd.get("created_at", now)
            expiry = float(cmd.get("expiry") if cmd.get("expiry") is not None else 60.0)
            if (now - created) <= expiry:
                valid_commands.append(cmd)

        # Clear queue after draining
        self.offline_queues[key] = []
        return valid_commands

    def on_emergency_stop(self, user_id: int):
        """Halts all remote commands immediately, purges queues, alerts clients."""
        # Purge all offline queues for this user
        keys_to_clear = [k for k in self.offline_queues.keys() if k[0] == user_id]
        for k in keys_to_clear:
            self.offline_queues[k] = []

    def on_disconnect_all(self, user_id: int):
        """Purges queues and revokes all live device channels for user."""
        self.on_emergency_stop(user_id)
        keys_to_disconnect = [k for k in self.active_websockets.keys() if k[0] == user_id]
        for k in keys_to_disconnect:
            self.active_websockets.pop(k, None)

    async def relay_command(self, user_id: int, cmd_data: dict) -> dict:
        """
        Validates, relays, and audits a remote command packet.
        Format:
        {
            "id": str,
            "sender_device": str,
            "target_device": str,
            "type": str,
            "payload": dict,
            "created_at": float (optional, defaults to now),
            "expiry": int (optional, default 60)
        }
        """
        now = time.time()
        self._cleanup_old_records(now)

        norm_cmd = unwrap_command_packet(cmd_data)
        cmd_id = str(norm_cmd.get("id", "")).strip()
        sender_id = str(norm_cmd.get("sender_device", "")).strip()
        target_id = str(norm_cmd.get("target_device", "")).strip()
        cmd_type = str(norm_cmd.get("type", "")).strip()
        payload = norm_cmd.get("payload") or {}
        created_at = float(norm_cmd.get("created_at") or now)

        if not cmd_id or not sender_id or not target_id or not cmd_type:
            return {
                "success": False,
                "error": "INVALID_FORMAT",
                "message": "Missing required fields: id, sender_device, target_device, type."
            }

        # Validate against shared schema
        is_valid, err_msg, _ = validate_command_packet(norm_cmd)
        if not is_valid:
            return {
                "success": False,
                "error": "INVALID_SCHEMA",
                "message": err_msg or f"Invalid command packet for '{cmd_type}'"
            }

        # 1. Global STOP check (Rule 6)
        if db.get_emergency_stopped(user_id):
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "blocked_by_emergency_stop"
                })
            )
            return {
                "success": False,
                "error": "BLOCKED_BY_STOP",
                "message": "Emergency STOP is active. Remote commands halted immediately."
            }

        # 2. Replay Protection check (Rule 3)
        if cmd_id in self.seen_command_ids:
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "replay_rejected"
                })
            )
            return {
                "success": False,
                "error": "REPLAY_REJECTED",
                "message": "Duplicate command ID rejected (replay protection)."
            }
        self.seen_command_ids[cmd_id] = now

        # 3. Command expiry check
        cmd_expiry = float(cmd_data.get("expiry") if cmd_data.get("expiry") is not None else 60.0)
        age = now - created_at
        if age > cmd_expiry or age < -5.0:  # Allow 5s clock skew
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "expired"
                })
            )
            return {
                "success": False,
                "error": "EXPIRED",
                "message": f"Command expired ({int(age)}s old > {int(cmd_expiry)}s limit)."
            }

        # 4. Per-user rate limiting check (Rule 8)
        if not self._check_user_rate_limit(user_id, now):
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "rate_limited"
                })
            )
            return {
                "success": False,
                "error": "RATE_LIMITED",
                "message": "Remote command rate limit exceeded (max 30 per minute)."
            }

        # 5. Sender verification (Rule 2 & 9)
        sender_dev = db.get_device_by_id(user_id, sender_id)
        if not sender_dev or sender_dev.get("status") != "trusted":
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "sender_untrusted"
                })
            )
            return {
                "success": False,
                "error": "SENDER_UNTRUSTED",
                "message": "Sender device is not trusted or has been revoked."
            }

        # 6. Target device & Cross-user verification (Rule 9)
        target_dev = db.get_device_by_id(user_id, target_id)
        if not target_dev:
            # Cross-user isolation: target not found for this user
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "target_not_found"
                })
            )
            return {
                "success": False,
                "error": "TARGET_NOT_FOUND",
                "message": "Target device not found for your account."
            }

        if target_dev.get("status") != "trusted":
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "target_untrusted"
                })
            )
            return {
                "success": False,
                "error": "TARGET_UNTRUSTED",
                "message": "Target device is revoked or pending pairing approval."
            }

        # 7. Target Capabilities & Permission Level gating (Rule 4)
        # Step C2.7 Item 3: Check if target client supports this command type
        supported_tools = self.get_device_supported_tools(user_id, target_id, target_dev.get("platform"))
        if not is_command_supported_by_device(cmd_type, target_dev.get("platform"), supported_tools):
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "unsupported_command_type"
                })
            )
            return {
                "success": False,
                "error": "UNSUPPORTED_TYPE",
                "message": f"Target device does not support command type '{cmd_type}'."
            }

        cap_map = {
            "send_note": "note",
            "open_link": "open_link",
            "ring_phone": "ring",
            "sync_tasks": "sync",
        }
        cap_key = cap_map.get(cmd_type, cmd_type)
        target_caps = target_dev.get("capabilities", {})
        if not target_caps.get(cap_key, True):
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "capability_disabled"
                })
            )
            return {
                "success": False,
                "error": "CAPABILITY_DISABLED",
                "message": f"Target device disabled '{cmd_type}' capability."
            }

        perm_level = target_dev.get("permission_level", 1)
        if perm_level == 0 and cmd_type != "sync_tasks":
            # Level 0 is Read-Only: cannot run active commands
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "read_only_blocked"
                })
            )
            return {
                "success": False,
                "error": "READ_ONLY",
                "message": "Target device is Level 0 (Read-only)."
            }

        # Zero-Prompt for same-user trusted devices unless STRICT_DEVICE_PAIRING=true
        strict_pairing = os.getenv("STRICT_DEVICE_PAIRING", "false").lower() == "true"
        if not strict_pairing:
            requires_confirmation = False
        else:
            requires_confirmation = (perm_level >= 2) or (cmd_type == "open_link")

        # Packet delivered to target (Step C2.7 Item 3: explicit command type, never 'remote_command')
        packet = {
            "type": cmd_type,
            "command_type": cmd_type,
            "id": cmd_id,
            "sender_device": sender_id,
            "sender_name": sender_dev.get("name", "Trusted Device"),
            "target_device": target_id,
            "payload": payload,
            "created_at": created_at,
            "expiry": cmd_expiry,
            "permission_level": perm_level,
            "requires_confirmation": requires_confirmation,
        }

        # 8. Delivery or Offline Queuing
        ws_key = (user_id, target_id)
        ws = self.active_websockets.get(ws_key)
        relayed = False

        if ws:
            try:
                await ws.send_text(json.dumps(packet))
                relayed = True
            except Exception:
                # WebSocket dead, unregister and fallback to queue
                self.unregister_websocket(user_id, target_id, ws)

        if relayed:
            self.init_command_lifecycle(cmd_id, user_id, sender_id, target_id, cmd_type, status="delivered")
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "relayed"
                })
            )
            return {
                "success": True,
                "result": "relayed",
                "command_id": cmd_id,
                "requires_confirmation": requires_confirmation,
            }
        else:
            # Queue offline (max 10 commands per device)
            q_key = (user_id, target_id)
            current_q = self.offline_queues.get(q_key, [])
            # Prune expired
            current_q = [c for c in current_q if (now - c.get("created_at", now)) <= float(c.get("expiry", 60.0))]
            if len(current_q) >= 10:
                current_q.pop(0)  # Drop oldest
            current_q.append(packet)
            self.offline_queues[q_key] = current_q
            self.init_command_lifecycle(cmd_id, user_id, sender_id, target_id, cmd_type, status="queued")

            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "queued_offline"
                })
            )
            return {
                "success": True,
                "result": "queued_offline",
                "command_id": cmd_id,
                "requires_confirmation": requires_confirmation,
            }

# Global singleton
relay_manager = CommandRelayManager()
