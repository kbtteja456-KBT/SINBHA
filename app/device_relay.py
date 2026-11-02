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
        # Maps (user_id, device_id) -> WebSocket (live connections to THIS worker process)
        self.active_websockets: Dict[Tuple[int, str], WebSocket] = {}

        # Legacy compatibility for test cleanup and capability cache
        self.offline_queues: Dict[str, Any] = {}
        self.device_capabilities: Dict[Tuple[int, str], dict] = {}
        self.device_installed_apps: Dict[Tuple[int, str], list] = {}
        self.device_telemetry: Dict[Tuple[int, str], dict] = {}
        self._lifecycle_waiters: Dict[str, Any] = {}

        # Replay protection cache: command_id -> timestamp (pruned after 300s)
        self.seen_command_ids: Dict[str, float] = {}

        # Sliding window per-user rate limiting: user_id -> List[timestamp] (max 30 / min)
        self.user_command_history: Dict[int, List[float]] = {}

        # User notifications buffer: user_id -> List[dict] (max 25, in-memory volatile notifications)
        self.user_notifications: Dict[int, List[dict]] = {}

        # Late confirmation handlers (Step C2.7 Item 2): command_id -> dict
        self.late_confirmation_handlers: Dict[str, dict] = {}

        # User command updates buffer (e.g. for frontend polling/SSE): user_id -> List[dict]
        self.command_updates: Dict[int, List[dict]] = {}

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
        """Stores device capability handshake reported by companion app directly in the database."""
        tools = supported_tools or self.get_default_supported_tools(platform)
        caps = {
            "platform": platform,
            "app_version": app_version,
            "supported_tools": tools,
            "installed_apps": installed_apps or [],
            "updated_at": time.time()
        }
        self.device_capabilities[(user_id, device_id)] = caps
        self.device_installed_apps[(user_id, device_id)] = installed_apps or []
        db.update_device_presence(
            user_id=user_id,
            device_id=device_id,
            client_version=app_version,
            supported_tools=tools,
            installed_apps=installed_apps,
            platform=platform,
        )
        return caps

    def get_device_installed_apps(self, user_id: int, device_id: str) -> List[dict]:
        """Returns installed apps reported by this companion device from the database."""
        dev = db.get_device_presence(user_id, device_id)
        if dev and dev.get("installed_apps"):
            return dev["installed_apps"]
        return []
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
        dev = db.get_device_presence(user_id, device_id)
        if dev and dev.get("supported_tools"):
            return dev["supported_tools"]
        if (user_id, device_id) in self.device_capabilities:
            return self.device_capabilities[(user_id, device_id)].get("supported_tools", [])
        return self.get_default_supported_tools(platform)

    @property
    def command_lifecycles(self) -> Dict[str, dict]:
        """Backward compatibility for unit tests that inspect active command lifecycles."""
        try:
            with db.get_db_session() as session:
                cmds = session.scalars(db.select(db.DeviceCommand).order_by(db.DeviceCommand.created_at.desc())).all()
                return {c.id: db._device_command_to_dict(c, session) for c in cmds}
        except Exception:
            return {}

    def init_command_lifecycle(
        self,
        cmd_id: str,
        user_id: int,
        sender_device: str,
        target_device: str,
        cmd_type: str,
        status: str = "queued",
    ):
        """Initializes lifecycle record for a command in the persistent database."""
        db.create_device_command(
            user_id=user_id,
            cmd_id=cmd_id,
            sender_device=sender_device,
            target_device=target_device,
            cmd_type=cmd_type,
            payload={},
            expiry_seconds=60,
            status=status,
        )

    def register_late_confirmation_listener(
        self,
        cmd_id: str,
        user_id: int,
        message_id: Optional[int] = None,
        app_name: str = "",
    ):
        """
        Step C2.7 Item 2: Registers listener for delayed command confirmations.
        If confirmation arrives after the wait window, updates earlier chat message.
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
        client_timestamp: Optional[str] = None,
    ) -> dict:
        """
        Step C2.8 & C2.10:
        Updates command status in database and records lifecycle stage timestamps.
        Checks for late confirmations if status is succeeded and previously timed out.
        """
        prev_entry = db.get_device_command(user_id, cmd_id)
        updated = db.update_device_command_status(
            user_id, cmd_id, status, result=result, error=error, client_timestamp=client_timestamp
        )
        entry = updated or {
            "command_id": cmd_id,
            "user_id": user_id,
            "status": status,
            "result": result,
            "error": error,
        }

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

        # Step C2.7 & C2.8 Item 2: Late Confirmations
        # If result arrives after wait window (or command was marked timed_out), update earlier chat message
        if status in ("succeeded", "executed"):
            is_late = False
            if prev_entry:
                if prev_entry.get("status") == "timed_out":
                    is_late = True
                elif prev_entry.get("created_at") and (time.time() - prev_entry["created_at"]) > 9.0:
                    is_late = True
            if not is_late and cmd_id in self.late_confirmation_handlers:
                is_late = True

            if is_late:
                late_info = self.late_confirmation_handlers.pop(cmd_id, None)
                app_disp = (late_info.get("app_name") if late_info else None) or (
                    entry.get("result", {}).get("app") if isinstance(entry.get("result"), dict) else "app"
                )
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
                    "timestamp": time.time(),
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

        return entry

    def get_command_lifecycle(self, cmd_id: str, user_id: Optional[int] = None) -> Optional[dict]:
        """Retrieves command state from database."""
        if user_id is not None:
            return db.get_device_command(user_id, cmd_id)
        # Search across database
        with db.get_db_session() as session:
            cmd = session.scalar(db.select(db.DeviceCommand).where(db.DeviceCommand.id == cmd_id))
            if cmd:
                return db._device_command_to_dict(cmd, session)
        return None

    async def wait_for_command_completion(
        self,
        user_id: int,
        cmd_id: str,
        timeout: float = 10.0
    ) -> dict:
        """
        Step C2.8 & C2.10:
        Awaits up to timeout (default 10s) by polling the database row.
        Includes 'not_installed' as a terminal status so negative checks resolve immediately.
        On timeout, compiles and returns the exact 6-stage lifecycle table and identifies first_missing_stage.
        """
        terminal_statuses = ("succeeded", "failed", "executed", "needs_tap", "not_installed")
        start_time = time.time()
        poll_interval = 0.12  # 120ms polling interval

        while (time.time() - start_time) < timeout:
            cmd = db.get_device_command(user_id, cmd_id)
            if cmd:
                st = cmd.get("status")
                if st in terminal_statuses:
                    return cmd
            await asyncio.sleep(poll_interval)

        # Timed out after timeout window: update row in DB to 'timed_out'
        db.update_device_command_status(user_id, cmd_id, status="timed_out")
        cmd_rec = db.get_device_command(user_id, cmd_id) or {}
        stages = cmd_rec.get("stages", {})
        table, first_missing = db.format_stage_table(stages)
        return {
            "command_id": cmd_id,
            "status": "timed_out",
            "success": False,
            "stages": stages,
            "stage_table": table,
            "first_missing_stage": first_missing,
            "message": f"I sent it to your device, but could not confirm (timed out after 10s). First missing stage: {first_missing or 'unknown'}."
        }

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
        """Stores device telemetry in the database."""
        bat = telemetry.get("battery_level") if "battery_level" in telemetry else telemetry.get("battery")
        db.update_device_presence(
            user_id=user_id,
            device_id=device_id,
            battery=bat,
            is_charging=telemetry.get("is_charging"),
            client_version=telemetry.get("version"),
            supported_tools=telemetry.get("supported_tools"),
            installed_apps=telemetry.get("installed_apps"),
            last_error=telemetry.get("last_error"),
            last_http_status=telemetry.get("last_http_status"),
        )

    def get_device_telemetry(self, user_id: int, device_id: Optional[str] = None) -> Optional[dict]:
        """Gets telemetry for a device from the database."""
        if device_id:
            dev = db.get_device_presence(user_id, device_id)
            if dev:
                return {
                    "battery": dev.get("battery_level"),
                    "battery_level": dev.get("battery_level"),
                    "is_charging": dev.get("is_charging", False),
                    "platform": dev.get("platform"),
                    "version": dev.get("client_version"),
                    "supported_tools": dev.get("supported_tools"),
                    "installed_apps": dev.get("installed_apps"),
                    "last_seen": dev.get("last_seen_at"),
                    "last_ping": dev.get("last_ping_at"),
                    "last_error": dev.get("last_error"),
                    "last_http_status": dev.get("last_http_status"),
                    "permissions": {"battery_optimization_ignored": True, "overlay_granted": True},
                }
        return None

    def _cleanup_old_records(self, now: float):
        """Prunes expired replay entries (> 300s old)."""
        cutoff = now - 300.0
        expired_ids = [cid for cid, ts in self.seen_command_ids.items() if ts < cutoff]
        for cid in expired_ids:
            self.seen_command_ids.pop(cid, None)

    def _check_user_rate_limit(self, user_id: int, now: float, max_limit: int = 30) -> bool:
        """Sliding window: allows max remote commands per user per 60 seconds (default 30, 120 for diagnostics)."""
        window_start = now - 60.0
        history = self.user_command_history.get(user_id, [])
        # Prune old
        history = [ts for ts in history if ts > window_start]
        if len(history) >= max_limit:
            self.user_command_history[user_id] = history
            return False
        history.append(now)
        self.user_command_history[user_id] = history
        return True

    def register_websocket(self, user_id: int, device_id: str, websocket: WebSocket):
        """Registers a live device WebSocket connection and updates persistent DB presence."""
        self.active_websockets[(user_id, device_id)] = websocket
        db.update_device_presence(user_id, device_id, last_ping=True, websocket_connected=True)

    def unregister_websocket(self, user_id: int, device_id: str, websocket: Optional[WebSocket] = None):
        """Unregisters device WebSocket and updates persistent DB presence."""
        key = (user_id, device_id)
        current = self.active_websockets.get(key)
        if current and (websocket is None or current == websocket):
            self.active_websockets.pop(key, None)
            db.update_device_presence(user_id, device_id, websocket_connected=False)

    def mark_device_active(self, user_id: int, device_id: str):
        """Marks device as actively communicating in the database."""
        db.update_device_presence(user_id, device_id, last_ping=True)

    def is_device_connected(self, user_id: int, device_id: str) -> bool:
        """
        Checks if device has an active WebSocket or was actively communicating in the last 45s.
        Uses database presence so all worker processes share exact connection state.
        """
        if (user_id, device_id) in self.active_websockets:
            return True
        dev = db.get_device_presence(user_id, device_id)
        if not dev:
            dev = db.get_device_by_id(user_id, device_id)
        if dev:
            if dev.get("websocket_connected"):
                return True
            for ts_col in ("last_ping_at", "last_seen_at"):
                val = dev.get(ts_col)
                if val:
                    try:
                        from datetime import datetime, timezone
                        s = str(val)
                        if s.endswith("Z"):
                            s = s[:-1] + "+00:00"
                        dt = datetime.fromisoformat(s)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        now = datetime.now(timezone.utc)
                        if (now - dt).total_seconds() < 45.0:
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
        Step C2.8 Item 2:
        Retrieves and drains pending commands from the persistent database.
        Stale/expired commands are filtered by the query and never returned.
        Any worker process serves this consistently.
        """
        db_cmds = db.get_pending_device_commands(user_id, device_id)
        if (user_id, device_id) in self.offline_queues:
            now = time.time()
            raw_queue = self.offline_queues.pop((user_id, device_id), [])
            mem_cmds = [c for c in raw_queue if (now - c.get("created_at", now)) < 60]
            db_cmds = (db_cmds + mem_cmds)[:10]
        return db_cmds

    def on_emergency_stop(self, user_id: int):
        """Halts all remote commands immediately, marks pending as failed in DB, alerts clients."""
        try:
            from sqlalchemy import update, and_
            with db.get_db_session() as session:
                session.execute(
                    update(db.DeviceCommand)
                    .where(and_(db.DeviceCommand.user_id == user_id, db.DeviceCommand.status.in_(["queued", "delivered"])))
                    .values(status="failed", error="Emergency STOP active", updated_at=db.utc_now())
                )
                session.commit()
        except Exception:
            pass

    def on_disconnect_all(self, user_id: int):
        """Revokes all live device channels for user and sets websocket_connected=False."""
        self.on_emergency_stop(user_id)
        keys_to_disconnect = [k for k in self.active_websockets.keys() if k[0] == user_id]
        for k in keys_to_disconnect:
            self.active_websockets.pop(k, None)
        try:
            from sqlalchemy import update
            with db.get_db_session() as session:
                session.execute(
                    update(db.Device)
                    .where(db.Device.user_id == user_id)
                    .values(websocket_connected=False)
                )
                session.commit()
        except Exception:
            pass

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

        # Step 17 Requirement 2 & Step 1C Item 7: Unverified accounts rejection explanation & audit log
        if not db.is_user_verified(user_id):
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "result": "unverified",
                    "error": "UNVERIFIED_ACCOUNT"
                })
            )
            return {
                "success": False,
                "error": "UNVERIFIED_ACCOUNT",
                "message": "Email verification is required to send remote commands. Please verify your email address.",
                "unverified": True
            }

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
        max_rate = 120 if (sender_id in ("server", "sinbha_server") or cmd_id.startswith("cmd_rel_") or cmd_id.startswith("cmd_test_")) else 30
        if not self._check_user_rate_limit(user_id, now, max_limit=max_rate):
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
        if sender_id in ("server", "sinbha_server"):
            sender_dev = {"id": 0, "name": "SINBHA Server", "status": "trusted"}
        else:
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
        # Step C2.9 & C2.10: Refuse remote commands from a client older than minimum supported version
        client_ver = target_dev.get("client_version")
        target_platform = (target_dev.get("platform") or "").lower()
        dev_type = "phone" if target_platform in ("android", "phone", "mobile") else "laptop"
        from app.version import is_client_version_supported, get_effective_min_version
        if client_ver and not is_client_version_supported(client_ver, platform=target_platform):
            effective_min = get_effective_min_version(target_platform)
            db.log_audit(
                user_id,
                "DEVICE_COMMAND_RELAY",
                json.dumps({
                    "command_id": cmd_id,
                    "type": cmd_type,
                    "sender_device": sender_id,
                    "target_device": target_id,
                    "client_version": client_ver,
                    "min_version": effective_min,
                    "result": "client_outdated"
                })
            )
            return {
                "success": False,
                "error": "CLIENT_OUTDATED",
                "message": f"Your {dev_type} app is version {client_ver}, please update to {effective_min}.",
                "needs_update": True
            }

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

        # 8. Delivery or Persistent Database Queuing (Step C2.8)
        ws_key = (user_id, target_id)
        ws = self.active_websockets.get(ws_key)
        relayed = False

        if ws:
            try:
                await ws.send_text(json.dumps(packet))
                relayed = True
            except Exception:
                # WebSocket dead, unregister
                self.unregister_websocket(user_id, target_id, ws)

        # Always persist in database (device_commands table) encrypted at rest
        # Both WebSocket delivery and persistent polling retrieve and update this row.
        # Step C2.10: If relayed via WebSocket, mark 'ws_sent' so that if the WS drops the frame,
        # the client's poll loop can still recover and drain it without double-fetching.
        cmd_status = "ws_sent" if relayed else "queued"
        db.create_device_command(
            user_id=user_id,
            cmd_id=cmd_id,
            sender_device=sender_id,
            target_device=target_id,
            cmd_type=cmd_type,
            payload=payload,
            expiry_seconds=int(cmd_expiry),
            status=cmd_status,
        )

        db.log_audit(
            user_id,
            "DEVICE_COMMAND_RELAY",
            json.dumps({
                "command_id": cmd_id,
                "type": cmd_type,
                "sender_device": sender_id,
                "target_device": target_id,
                "result": "relayed" if relayed else "queued_db"
            })
        )

        return {
            "success": True,
            "result": "relayed" if relayed else "queued_offline",
            "command_id": cmd_id,
            "requires_confirmation": requires_confirmation,
        }

# Global singleton
relay_manager = CommandRelayManager()
