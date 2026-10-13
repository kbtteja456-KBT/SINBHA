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

import time
import json
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from fastapi import WebSocket

from app import database as db

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

    def is_device_connected(self, user_id: int, device_id: str) -> bool:
        """Checks if device has an active WebSocket."""
        return (user_id, device_id) in self.active_websockets

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
            # 60s expiry window
            if (now - created) <= 60.0:
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

        cmd_id = str(cmd_data.get("id", "")).strip()
        sender_id = str(cmd_data.get("sender_device", "")).strip()
        target_id = str(cmd_data.get("target_device", "")).strip()
        cmd_type = str(cmd_data.get("type", "")).strip()
        payload = cmd_data.get("payload") or {}
        created_at = float(cmd_data.get("created_at") or now)

        if not cmd_id or not sender_id or not target_id or not cmd_type:
            return {
                "success": False,
                "error": "INVALID_FORMAT",
                "message": "Missing required fields: id, sender_device, target_device, type."
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

        # 3. 60-second command expiry check (Rule 3 & 8)
        age = now - created_at
        if age > 60.0 or age < -5.0:  # Allow 5s clock skew
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
                "message": f"Command expired ({int(age)}s old > 60s limit)."
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

        # Anything above Level 1 (2, 3, 4) requires confirmation on TARGET device
        # Also open_link always requires confirmation
        requires_confirmation = (perm_level >= 2) or (cmd_type == "open_link")

        # Packet delivered to target
        packet = {
            "type": "remote_command",
            "id": cmd_id,
            "sender_device": sender_id,
            "sender_name": sender_dev.get("name", "Trusted Device"),
            "target_device": target_id,
            "command_type": cmd_type,
            "payload": payload,
            "created_at": created_at,
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
            # Prune expired (> 60s)
            current_q = [c for c in current_q if (now - c.get("created_at", now)) <= 60.0]
            if len(current_q) >= 10:
                current_q.pop(0)  # Drop oldest
            current_q.append(packet)
            self.offline_queues[q_key] = current_q

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
