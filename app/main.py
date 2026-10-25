import os
import json
import socket
import re
import datetime
from fastapi import FastAPI, HTTPException, Depends, Request, Response, status, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

# Load environment variables (.env)
load_dotenv()

import time
from fastapi.middleware.cors import CORSMiddleware

APP_START_TIME = time.time()

from app.ai_brain import (
    call_sinbha_brain,
    extract_explicit_facts,
    detect_fact_correction,
    is_forget_intent,
    find_target_fact_to_forget,
    parse_relative_date,
    parse_relative_datetime,
    find_matching_tasks,
    detect_task_chat_intent,
    get_llm_credentials,
)
from app import database as db
from app.search import (
    execute_web_search,
    detect_search_intent,
    detect_search_intent_smart,
)
from app.web_intelligence import (
    agent_instance,
    ResearchSearchRequest,
    ResearchSearchResponse,
    SearchDecisionEngine,
)
from app.device_relay import relay_manager
from app.security import (
    is_production,
    is_dev_mode_allowed,
    validate_production_config,
    check_endpoint_rate_limits,
    check_ai_usage_caps,
    get_daily_global_ai_limit,
    get_allowed_origins,
    SecurityHeadersAndCSRFMiddleware,
)

app = FastAPI(title="SINBHA - Personal AI Companion")

# CORS middleware for trusted client origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Step 11: Security Headers, Request Size Limiter & CSRF Protection Middleware
app.add_middleware(SecurityHeadersAndCSRFMiddleware)

@app.on_event("startup")
def on_app_startup():
    """
    Requirement 1: Config safety: refuses to start in production if required secrets are missing.
    """
    validate_production_config()
    db.init_db()

SESSION_COOKIE_NAME = "sinbha_session"

# ----------------- Request Models -----------------

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class SignupRequest(BaseModel):
    email: str
    password: str
    is_18: Optional[bool] = None
    is_18_or_older: Optional[bool] = None
    agreed_terms: Optional[bool] = None
    agree_terms: Optional[bool] = None
    timezone: Optional[str] = "UTC"

    def get_is_18(self) -> bool:
        if self.is_18 is not None:
            return self.is_18
        if self.is_18_or_older is not None:
            return self.is_18_or_older
        return False

    def get_agreed_terms(self) -> bool:
        if self.agreed_terms is not None:
            return self.agreed_terms
        if self.agree_terms is not None:
            return self.agree_terms
        return False

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    message: str
    tz_offset_minutes: Optional[int] = None
    tz_offset: Optional[int] = None
    timezone: Optional[str] = None

class ActionConfirmRequest(BaseModel):
    action: str  # "confirm" or "cancel"

class TaskActionRequest(BaseModel):
    proposal_id: Optional[int] = None
    reminders: Optional[list] = []

class TaskConfirmWithRemindersRequest(BaseModel):
    proposal_id: Optional[int] = None
    reminders: Optional[list] = []
    chosen_time: Optional[str] = None

class ReminderFiredRequest(BaseModel):
    task_id: int
    reminder_id: Optional[str] = None

class ReminderSnoozeRequest(BaseModel):
    task_id: int
    minutes: int = 15

class SettingsUpdateRequest(BaseModel):
    persistence: str = "normal"
    quiet_hours_enabled: str = "true"
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    country: Optional[str] = "US"
    timezone: Optional[str] = "UTC"
    web_search_enabled: Optional[str] = "true"

class TaskStatusUpdateRequest(BaseModel):
    status: str  # "pending" or "completed"

class FactCreateRequest(BaseModel):
    fact: str
    category: Optional[str] = "general"

class FactUpdateRequest(BaseModel):
    fact: str

# Step 16 / 16b: Device & Command Request Models
class DeviceRegisterRequest(BaseModel):
    device_id: str
    name: Optional[str] = "Web Companion"
    platform: Optional[str] = "web"
    password: Optional[str] = None
    is_signup: Optional[bool] = False

class DevicePairApproveRequest(BaseModel):
    code: str
    approver_device_id: Optional[str] = None

class DeviceUpdateRequest(BaseModel):
    name: Optional[str] = None
    permission_level: Optional[int] = None
    capabilities: Optional[dict] = None
    password: Optional[str] = None

class DeviceCommandRequest(BaseModel):
    id: str
    sender_device: str
    target_device: str
    type: str
    payload: Optional[dict] = {}
    created_at: Optional[float] = None
    expiry: Optional[int] = 60

class DeviceCommandAckRequest(BaseModel):
    status: str = "executed"
    details: Optional[str] = ""

def get_local_ip():
    """Finds the local network IP so you can open the app on your phone."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def is_dev_mode_active() -> bool:
    """Checks if DEV_MODE is enabled and allowed (always False in production)."""
    return is_dev_mode_allowed()

# ----------------- Authentication & Session Dependency (Step 9) -----------------

def get_client_ip(request: Request) -> str:
    """Extracts client IP address for rate limiting."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

async def get_current_user_optional(request: Request) -> Optional[dict]:
    """Retrieves logged-in user if session is valid; else returns None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if not token:
        return None
    # Requirement 3: Device tokens cannot access full user session endpoints
    if token.startswith("snb_dev_"):
        raise HTTPException(
            status_code=403,
            detail="Device token scope is restricted strictly to reminder actions (fetch reminders, Done, Snooze). Full user session required."
        )
    return db.get_user_by_session(token)

async def get_current_user(request: Request) -> dict:
    """Dependency that enforces authenticated user. Rejects with 401 if not logged in."""
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user

async def get_reminder_action_user(request: Request) -> dict:
    """
    Requirement 3: Dedicated dependency for mobile companion reminder actions.
    Accepts full web session tokens OR scoped mobile device tokens (snb_dev_...).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Please provide a valid session or device token.")

    if token.startswith("snb_dev_"):
        user = db.get_user_by_device_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired device token. Please log into the app again.")
        return user

    user = db.get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user

# ----------------- Auth Endpoints (Step 9 & 11) -----------------

@app.post("/api/auth/signup")
async def signup_endpoint(payload: SignupRequest, request: Request, response: Response):
    """
    Requirement 1 & 7: User registration with email + password (min 8 chars, argon2 hash),
    checkboxes for 18+ and Terms/Privacy agreement.
    Requirement 4: Rate limited.
    """
    check_endpoint_rate_limits(request)
    try:
        user = db.create_user(
            email=payload.email,
            password=payload.password,
            is_18=payload.get_is_18(),
            agreed_terms=payload.get_agreed_terms(),
            timezone_name=payload.timezone or "UTC"
        )
        token = db.create_session(user["id"])
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=is_production(),
            max_age=14 * 86400,
            path="/"
        )
        return {
            "success": True,
            "user": user,
            "message": "Account created successfully! 🌸 Welcome to SINBHA."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create account: {e}")

@app.post("/api/auth/login")
async def login_endpoint(payload: LoginRequest, request: Request, response: Response):
    """
    Requirement 1 & 2: User login with argon2 password verification,
    secure sessions (httpOnly, SameSite, Secure in production), and rate limiting.
    """
    check_endpoint_rate_limits(request)
    client_ip = get_client_ip(request)
    try:
        user = db.authenticate_user(payload.email, payload.password, client_ip=client_ip)
        token = db.create_session(user["id"])
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=is_production(),
            max_age=14 * 86400,
            path="/"
        )
        return {
            "success": True,
            "user": user,
            "message": "Welcome back! 🌸"
        }
    except ValueError as e:
        msg = str(e)
        if "Too many failed" in msg or "lockout" in msg.lower() or "try again after" in msg.lower():
            raise HTTPException(status_code=429, detail=msg)
        raise HTTPException(status_code=401, detail=msg)

@app.post("/api/auth/logout")
async def logout_endpoint(request: Request, response: Response):
    """
    Requirement 3: Logs out user by destroying session token.
    Also revokes associated mobile companion device tokens.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    auth_header = request.headers.get("Authorization")
    dev_token = None
    if auth_header and auth_header.startswith("Bearer "):
        val = auth_header[7:].strip()
        if val.startswith("snb_dev_"):
            dev_token = val
        elif not token:
            token = val

    x_dev_token = request.headers.get("x-device-token")
    if x_dev_token and not dev_token:
        dev_token = x_dev_token.strip()

    if token:
        db.delete_session(token)

    if dev_token:
        # Requirement 1: Revoke only this device's token, not other devices!
        db.revoke_device_token(dev_token)

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"success": True, "message": "Logged out successfully 🌸"}

@app.get("/api/auth/me")
async def get_me_endpoint(request: Request):
    """Returns currently logged-in user info or logged_in=False."""
    user = await get_current_user_optional(request)
    if not user:
        return {"logged_in": False, "user": None}
    return {
        "logged_in": True,
        "user": user
    }

@app.post("/api/account/change-password")
async def change_password_endpoint(payload: ChangePasswordRequest, request: Request, response: Response, user: dict = Depends(get_current_user)):
    """
    Requirement 9: Invalidate sessions on password change and update credentials.
    """
    check_endpoint_rate_limits(request, user_id=user["id"])
    try:
        db.change_user_password(user["id"], payload.old_password, payload.new_password)
        new_token = db.create_session(user["id"])
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=new_token,
            httponly=True,
            samesite="lax",
            secure=is_production(),
            max_age=14 * 86400,
            path="/"
        )
        return {"success": True, "message": "Password changed successfully! All other sessions have been logged out."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/account/export")
async def export_account_endpoint(request: Request, user: dict = Depends(get_current_user)):
    """
    Requirement 7: 'Download my data' (JSON export of the user's own data).
    """
    check_endpoint_rate_limits(request, user_id=user["id"])
    data = db.export_user_data(user["id"])
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename=sinbha_export_user_{user['id']}.json"}
    )

@app.delete("/api/account")
@app.post("/api/account/delete")
async def delete_account_endpoint(response: Response, user: dict = Depends(get_current_user)):
    """
    Requirement 7 & 8: 'Delete my account and all my data' with permanent removal.
    """
    user_id = user["id"]
    db.log_audit(user_id, "ACCOUNT_DELETED", "User permanently erased account and all personal data.")
    db.delete_user_account(user_id)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"success": True, "status": "ok", "message": "Your account and all associated data have been permanently erased."}

@app.get("/api/legal")
async def legal_endpoint():
    """
    Requirement 14: Legal disclosures and terms summary.
    """
    return {
        "notice": "Marked for Legal Review",
        "companion_nature": "SINBHA is an automated AI personal assistant, not a licensed therapist, healthcare provider, or emergency crisis service.",
        "age_requirement": 18,
        "ai_processing": "User messages are processed by external AI model providers (e.g. OpenRouter/Google) to interpret tasks and generate replies.",
        "data_storage": "Data is stored with field-level encryption at rest in PostgreSQL.",
        "data_rights": "Users can download full data exports at /api/account/export and delete all data at /api/account/delete."
    }

# ----------------- Chat & Message Endpoints (Per-User) -----------------

@app.get("/api/messages")
async def get_messages_endpoint(user: dict = Depends(get_current_user)):
    """Returns stored conversation history for the logged-in user."""
    user_id = user["id"]
    msgs = db.get_all_messages(user_id)
    stopped = db.get_emergency_stopped(user_id)
    return {"messages": msgs, "emergency_stopped": stopped}

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest, request: Request, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    user_msg = payload.message.strip()

    # Requirement 5: Input limit (maximum 2,000 characters)
    if len(user_msg) > 2000:
        raise HTTPException(
            status_code=400,
            detail="Message is too long. Please keep your message under 2,000 characters. 🌸"
        )

    # Requirement 4: Rate limit check
    check_endpoint_rate_limits(request, user_id=user_id)

    if not user_msg:
        return JSONResponse({
            "reply": "I'm listening whenever you want to talk 🌸",
            "proposal": None
        })

    # Requirement 4: Per-user daily AI message limit and global cost cap kill switch
    user_today = db.get_user_today_message_count(user_id)
    global_today = db.get_global_today_message_count()
    allowed, friendly_notice = check_ai_usage_caps(user_today, global_today)
    if not allowed:
        db.save_message(user_id, "user", user_msg)
        db.save_message(user_id, "assistant", friendly_notice)
        return JSONResponse({
            "reply": friendly_notice,
            "proposal": None
        })

    
    # RULE 3 & 7: STOP check comes FIRST (Per-User)
    if user_msg.upper() == "STOP":
        db.set_emergency_stopped(user_id, True)
        db.save_message(user_id, "user", user_msg)
        
        relay_manager.on_emergency_stop(user_id)
        db.cancel_pending_proposal(user_id, reason="Emergency STOP command received in chat")
        db.cancel_pending_task_action(user_id, reason="Emergency STOP command received in chat")
        
        stop_reply = "🛑 STOP command received. All operations halted immediately. Type any message or click 'Resume Chat' to continue whenever you're ready 🌸"
        db.save_message(user_id, "assistant", stop_reply)
        db.log_audit(user_id, "STOP_TRIGGERED", "User commanded STOP in chat.")
        return JSONResponse({
            "reply": stop_reply,
            "proposal": None,
            "stopped": True
        })

    # If stopped previously and user sends a normal message, automatically resume
    if db.get_emergency_stopped(user_id):
        db.set_emergency_stopped(user_id, False)
        db.log_audit(user_id, "STOP_RESUMED", "Chat resumed by normal message.")

    # 1. Check for pending task action confirmation in chat (complete or delete)
    pending_task_act = db.get_pending_task_action(user_id)
    if pending_task_act:
        lower_msg = user_msg.lower()
        is_confirm = bool(re.search(r"^(yes|yeah|yep|yup|confirm|sure|mark\s+it|do\s+it|delete\s+it|remove\s+it|please\s+do)\b", lower_msg))
        is_cancel = bool(re.search(r"^(no|nope|cancel|don't|drop\s+it|nevermind|nah|mat\s+karo)\b", lower_msg))

        if is_confirm:
            res = db.confirm_pending_task_action(user_id)
            if res:
                db.save_message(user_id, "user", user_msg)
                if res["action_type"] == "task_complete":
                    reply_msg = f"Woohoo! 🎉 Marked '{res['task_title']}' as completed! Amazing job! 🌸"
                else:
                    reply_msg = f"I've removed '{res['task_title']}' from your tasks 🌸"
                db.save_message(user_id, "assistant", reply_msg)
                return JSONResponse({
                    "reply": reply_msg,
                    "proposal": None,
                    "task_action_performed": res
                })
        elif is_cancel:
            db.cancel_pending_task_action(user_id, reason="User cancelled in chat")
            db.save_message(user_id, "user", user_msg)
            reply_msg = "No problem at all! Kept it just as it is 🌸"
            db.save_message(user_id, "assistant", reply_msg)
            return JSONResponse({
                "reply": reply_msg,
                "proposal": None,
                "action_cancelled": True
            })

    # 2. Check for pending task proposal confirmation in chat ("confirm", "yes", "save it" / "cancel", "no")
    pending_task = db.get_pending_proposal(user_id)
    if pending_task:
        lower_msg = user_msg.lower()
        is_task_confirm = bool(re.search(r"^(yes|yeah|yep|yup|confirm|sure|save\s+it|save\s+task|please\s+do|do\s+it|add\s+it)\b", lower_msg))
        is_task_cancel = bool(re.search(r"^(no|nope|cancel|don't\s+save|drop\s+it|nevermind|nah|mat\s+karo)\b", lower_msg))

        if is_task_confirm:
            confirmed = db.confirm_pending_proposal(user_id)
            if confirmed:
                db.save_message(user_id, "user", user_msg)
                reply_msg = f"Saved! I've added '{confirmed['title']}' to your tasks. You've got this! 🌸"
                db.save_message(user_id, "assistant", reply_msg)
                return JSONResponse({
                    "reply": reply_msg,
                    "proposal": None,
                    "task_confirmed": confirmed
                })
        elif is_task_cancel:
            db.cancel_pending_proposal(user_id, reason="User cancelled in chat")
            db.save_message(user_id, "user", user_msg)
            reply_msg = "No problem at all! I dropped that task proposal 🌸"
            db.save_message(user_id, "assistant", reply_msg)
            return JSONResponse({
                "reply": reply_msg,
                "proposal": None,
                "task_cancelled": True
            })

    # 3. Check for pending memory fact deletion confirmation
    pending_mem = db.get_pending_action(user_id)
    if pending_mem and pending_mem["action_type"] == "forget_fact":
        lower_msg = user_msg.lower()
        is_yes = bool(re.search(r"^(yes|yeah|yep|yup|sure|ok|okay|confirm|please|do it|forget it|delete it|ha|haan|yes please|definitely|go ahead)\b", lower_msg))
        is_no = bool(re.search(r"^(no|nope|cancel|don't|keep it|nevermind|nah|stop|mat karo)\b", lower_msg))

        if is_yes:
            target_id = pending_mem["target_id"]
            db.save_message(user_id, "user", user_msg)
            db.delete_fact(user_id, target_id)
            db.clear_pending_action(user_id)
            reply = "I've forgotten that for you! It's wiped from my memory 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({
                "reply": reply,
                "proposal": None,
                "action_performed": "fact_deleted",
                "deleted_fact_id": target_id
            })
        elif is_no:
            db.save_message(user_id, "user", user_msg)
            db.clear_pending_action(user_id)
            reply = "No problem at all! I'll keep remembering it 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({
                "reply": reply,
                "proposal": None,
                "action_performed": "cancelled"
            })
        else:
            db.clear_pending_action(user_id)

    # 3b. Check for pending remote command action confirmation (Step 16)
    if pending_mem and pending_mem["action_type"] == "remote_command":
        lower_msg = user_msg.lower()
        is_yes = bool(re.search(r"^(yes|yeah|yep|yup|sure|ok|okay|confirm|please|do it|run it|send it|ring it|go ahead)\b", lower_msg))
        is_no = bool(re.search(r"^(no|nope|cancel|don't|nevermind|nah|stop|mat karo)\b", lower_msg))

        if is_yes:
            cmd_data = json.loads(pending_mem["details"]) if pending_mem.get("details") else {}
            db.clear_pending_action(user_id)
            relay_res = await relay_manager.relay_command(user_id, cmd_data)
            db.save_message(user_id, "user", user_msg)
            if relay_res.get("success"):
                reply = f"🌸 Remote action sent to your device! ({cmd_data.get('type')})"
            else:
                reply = f"Could not execute remote command: {relay_res.get('message', 'Rejected')}"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({
                "reply": reply,
                "proposal": None,
                "remote_command_result": relay_res
            })
        elif is_no:
            db.save_message(user_id, "user", user_msg)
            db.clear_pending_action(user_id)
            reply = "Remote action cancelled 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({
                "reply": reply,
                "proposal": None,
                "action_performed": "cancelled"
            })
        else:
            db.clear_pending_action(user_id)


    # 4. Check for task completion or deletion intent through chat (Step 6)
    all_current_tasks = db.get_all_tasks(user_id)
    task_intent = detect_task_chat_intent(user_msg, all_current_tasks)
    
    if task_intent["intent"] == "complete":
        matched = task_intent["task"]
        db.set_pending_task_action(user_id, "task_complete", matched["id"], matched["title"])
        db.save_message(user_id, "user", user_msg)
        reply = f"Woohoo! That's awesome! 🎉 Should I mark '{matched['title']}' as done?"
        db.save_message(user_id, "assistant", reply)
        return JSONResponse({
            "reply": reply,
            "proposal": {
                "type": "task_complete",
                "task_id": matched["id"],
                "task_title": matched["title"],
                "prompt": f"Mark '{matched['title']}' as done?"
            }
        })
    elif task_intent["intent"] == "delete":
        matched = task_intent["task"]
        db.set_pending_task_action(user_id, "task_delete", matched["id"], matched["title"])
        db.save_message(user_id, "user", user_msg)
        reply = f"Are you sure you want me to remove '{matched['title']}' from your tasks? 🌸"
        db.save_message(user_id, "assistant", reply)
        return JSONResponse({
            "reply": reply,
            "proposal": {
                "type": "task_delete",
                "task_id": matched["id"],
                "task_title": matched["title"],
                "prompt": f"Delete '{matched['title']}'?"
            }
        })
    elif task_intent["intent"] == "ambiguous_complete":
        db.save_message(user_id, "user", user_msg)
        c_names = ", ".join([f"'{c['title']}'" for c in task_intent["candidates"]])
        reply = f"I found a few matching tasks: {c_names}. Which one did you finish? 🌸"
        db.save_message(user_id, "assistant", reply)
        return JSONResponse({"reply": reply, "proposal": None})
    elif task_intent["intent"] == "ambiguous_delete":
        db.save_message(user_id, "user", user_msg)
        c_names = ", ".join([f"'{c['title']}'" for c in task_intent["candidates"]])
        reply = f"I found a few matching tasks: {c_names}. Which one would you like to delete? 🌸"
        db.save_message(user_id, "assistant", reply)
        return JSONResponse({"reply": reply, "proposal": None})

    # 5. Check for memory forget request ("forget X", "forget that", "forget my name")
    facts = db.get_all_facts(user_id)
    if is_forget_intent(user_msg):
        db.save_message(user_id, "user", user_msg)
        if not facts:
            reply = "I don't have anything saved in my memory to forget right now! 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        target_fact = find_target_fact_to_forget(user_msg, facts)
        db.set_pending_action(user_id, "forget_fact", target_id=target_fact["id"], target_text=target_fact["fact"])
        
        reply = f"Are you sure you want me to forget that '{target_fact['fact']}'? Just reply \"yes\" or confirm to remove it 🌸"
        db.save_message(user_id, "assistant", reply)
        return JSONResponse({
            "reply": reply,
            "proposal": {
                "type": "confirm_forget",
                "fact_id": target_fact["id"],
                "fact_text": target_fact["fact"],
                "prompt": f"Forget '{target_fact['fact']}'?"
            }
        })

    # 6. Check for fact correction ("my name is Ravi, not Rahul")
    target_id, updated_text, _old_text = detect_fact_correction(user_msg, facts)
    if target_id and updated_text:
        db.save_message(user_id, "user", user_msg)
        db.update_fact(user_id, target_id, updated_text)
        
        updated_facts = db.get_all_facts(user_id)
        recent_history = db.get_recent_messages(user_id, limit=20)
        brain_result = await call_sinbha_brain(
            user_message=user_msg,
            chat_history=recent_history[:-1],
            remembered_facts=updated_facts
        )
        ai_reply = brain_result.get("reply", f"Got it! I've updated my memory: {updated_text} 🌸")
        db.save_message(user_id, "assistant", ai_reply)
        return JSONResponse({
            "reply": ai_reply,
            "proposal": None,
            "updated_fact": {"id": target_id, "fact": updated_text}
        })

    # 6b. Check for remote device action request (Step 16 / 16c Omnipresent Agent)
    # Security Rule 7: Text from web pages, emails, or untrusted external content must NEVER trigger remote actions!
    is_external_content = bool(re.search(r"(http[s]?://|forwarded message|from:|<email>|content from web)", user_msg, re.IGNORECASE))
    if not is_external_content:
        lower_m = user_msg.lower().strip()
        is_list_devices = bool(re.search(r"\b(what|which|show|list)\s+(are\s+)?(my\s+)?(devices|connected devices|devices connected)\b", lower_m))
        is_sync_intent = bool(re.search(r"\b(sync|synchronize)\s+(all\s+)?(my\s+)?(devices|phone and laptop|laptop and phone)\b", lower_m))
        is_open_app_intent = bool(re.search(r"\b(open|launch|start|run)\s+(the\s+)?(whatsapp|chrome|google\s+chrome|spotify|youtube|gmail|camera|notepad|calculator|calc|vscode|code|explorer|terminal|cmd|settings|maps)\b|\b(on\s+(my\s+)?(phone|mobile|android|laptop|pc|desktop)\s+(open|launch|start|run))\b", lower_m))
        is_lock_intent = bool(re.search(r"\b(lock|secure)\s+(my\s+)?(laptop|pc|desktop|computer|screen|workstation)\b", lower_m))
        is_battery_intent = bool(re.search(r"\b(check|what\s+is|show|get)\s+(the\s+)?(battery|battery\s+percentage|battery\s+level|charge)\b|\b(phone|laptop)\s+battery\b", lower_m))
        is_read_notifs_intent = bool(re.search(r"\b(read|check|show|get|what\s+are)\s+(my\s+)?(phone\s+)?(notifications|messages|notifs|whatsapp\s+messages|emails|mails|sms)\b|\bwhat\s+(messages|emails|notifications)\s+(do\s+i\s+have|came)\b", lower_m))
        is_ring_intent = bool(re.search(r"\b(ring|find|buzz|ping|alarm)\s+(my\s+)?(phone|device|mobile|laptop|pc)\b", lower_m))
        is_send_note_intent = bool(re.search(r"\b(send|push)\s+(a\s+)?(note|link|message)\s+to\s+(my\s+)?(phone|device|laptop|other\s+device)\b", lower_m))

        if is_list_devices:
            devs = db.get_user_devices(user_id)
            if not devs:
                reply = "You don't have any devices connected yet! Log into your account on your phone or laptop and they will auto-connect 🌸"
            else:
                lines = ["Here are your connected companion devices in your network: 🌸\n"]
                for d in devs:
                    is_online = relay_manager.is_device_connected(user_id, d.get("device_id"))
                    online_badge = "🟢 Online" if is_online else "⚪ Offline"
                    icon = "📱" if d.get("platform") == "android" else ("💻" if d.get("platform") == "windows" else "🌐")
                    tel = relay_manager.get_device_telemetry(user_id, d.get("device_id"))
                    bat_str = f" • 🔋 {tel['battery']}%" if (tel and tel.get("battery") is not None) else ""
                    lines.append(f"- {icon} **{d.get('name')}** ({online_badge}{bat_str}) [{d.get('status').capitalize()}]")
                reply = "\n".join(lines)
            db.save_message(user_id, "user", user_msg)
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        if is_sync_intent:
            devs = db.get_user_devices(user_id)
            for d in devs:
                if d.get("status") == "trusted":
                    await relay_manager.broadcast_event(user_id, "sync_tasks", {"reason": "chat_command"})
            reply = "🌸 Sent an instant synchronization signal to all your connected devices!"
            db.save_message(user_id, "user", user_msg)
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        if is_read_notifs_intent:
            all_user_devices = db.get_user_devices(user_id)
            trusted_devices = [d for d in all_user_devices if d.get("status") == "trusted"]
            for d in trusted_devices:
                if d.get("platform", "").lower() in ("android", "mobile"):
                    cmd_id = f"cmd_qry_{int(time.time()*1000)}"
                    await relay_manager.relay_command(user_id, {
                        "id": cmd_id,
                        "sender_device": trusted_devices[0]["device_id"],
                        "target_device": d["device_id"],
                        "type": "query_notifications",
                        "payload": {},
                        "created_at": time.time(),
                        "expiry": 30
                    })
            notifs = relay_manager.get_user_notifications(user_id)
            db.save_message(user_id, "user", user_msg)
            if notifs:
                lines = ["📬 **Recent Notifications from your Phone:**\n"]
                for n in notifs[:8]:
                    app_label = n.get("app", "App")
                    title = n.get("title", "")
                    text = n.get("text", "")
                    lines.append(f"• **[{app_label}]** {title}: {text}")
                reply = "\n".join(lines)
            else:
                reply = (
                    "📬 No recent notifications recorded from your phone yet! 🌸\n\n"
                    "**To enable notifications:**\n"
                    "1. Open the SINBHA app on your phone.\n"
                    "2. Allow **Notification Access** for SINBHA in your Android Settings.\n"
                    "Once enabled, incoming messages, WhatsApp alerts, and emails will automatically sync across all your devices!"
                )
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        if is_battery_intent:
            all_user_devices = db.get_user_devices(user_id)
            trusted_devices = [d for d in all_user_devices if d.get("status") == "trusted"]
            for d in trusted_devices:
                cmd_id = f"cmd_bat_{int(time.time()*1000)}"
                await relay_manager.relay_command(user_id, {
                    "id": cmd_id,
                    "sender_device": trusted_devices[0]["device_id"],
                    "target_device": d["device_id"],
                    "type": "get_battery",
                    "payload": {},
                    "created_at": time.time(),
                    "expiry": 30
                })
            lines = ["🔋 **Device Battery Status:**\n"]
            found = False
            for d in trusted_devices:
                tel = relay_manager.get_device_telemetry(user_id, d.get("device_id"))
                if tel and tel.get("battery") is not None:
                    icon = "📱" if d.get("platform") == "android" else "💻"
                    chg = " (⚡ Charging)" if tel.get("is_charging") else ""
                    lines.append(f"- {icon} **{d.get('name')}**: **{tel['battery']}%**{chg}")
                    found = True
            db.save_message(user_id, "user", user_msg)
            if found:
                reply = "\n".join(lines)
            else:
                reply = "🔋 Sent a battery query signal to your companion devices! Open or wake the device to refresh telemetry 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        if is_lock_intent:
            all_user_devices = db.get_user_devices(user_id)
            trusted_devices = [d for d in all_user_devices if d.get("status") == "trusted"]
            target_dev = None
            for d in trusted_devices:
                if d.get("platform", "").lower() in ("windows", "desktop", "laptop"):
                    target_dev = d
                    break
            db.save_message(user_id, "user", user_msg)
            if target_dev:
                cmd_id = f"cmd_lock_{int(time.time()*1000)}"
                await relay_manager.relay_command(user_id, {
                    "id": cmd_id,
                    "sender_device": trusted_devices[0]["device_id"],
                    "target_device": target_dev["device_id"],
                    "type": "system_control",
                    "payload": {"action": "lock_screen"},
                    "created_at": time.time(),
                    "expiry": 60
                })
                reply = f"🔒 Done! I've locked your {target_dev['name']} screen."
            else:
                reply = "I couldn't find a trusted Windows laptop/PC connected to lock! Please make sure your laptop is logged in to your account 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        if is_open_app_intent:
            all_user_devices = db.get_user_devices(user_id)
            trusted_devices = [d for d in all_user_devices if d.get("status") == "trusted"]
            app_match = re.search(r"\b(whatsapp|google\s+chrome|chrome|spotify|youtube|gmail|camera|notepad|calculator|calc|vscode|code|explorer|terminal|cmd|settings|maps)\b", lower_m)
            raw_app = app_match.group(1).lower() if app_match else "whatsapp"
            app_map = {
                "google chrome": "chrome",
                "calc": "calculator",
                "vscode": "code"
            }
            app_clean = app_map.get(raw_app, raw_app)
            target_dev = None
            wants_phone = bool(re.search(r"\b(phone|mobile|android|cell)\b", lower_m))
            wants_laptop = bool(re.search(r"\b(laptop|pc|desktop|windows|computer)\b", lower_m))
            if wants_laptop:
                for d in trusted_devices:
                    if d.get("platform", "").lower() in ("windows", "desktop", "laptop"):
                        target_dev = d
                        break
            elif wants_phone:
                for d in trusted_devices:
                    if d.get("platform", "").lower() in ("android", "mobile"):
                        target_dev = d
                        break
            else:
                if app_clean in ("camera",):
                    for d in trusted_devices:
                        if d.get("platform", "").lower() in ("android", "mobile"):
                            target_dev = d
                            break
                elif app_clean in ("notepad", "calculator", "code", "explorer", "terminal", "cmd"):
                    for d in trusted_devices:
                        if d.get("platform", "").lower() in ("windows", "desktop", "laptop"):
                            target_dev = d
                            break
                if not target_dev and trusted_devices:
                    target_dev = trusted_devices[-1] if len(trusted_devices) > 1 else trusted_devices[0]

            db.save_message(user_id, "user", user_msg)
            if target_dev:
                cmd_id = f"cmd_app_{int(time.time()*1000)}"
                await relay_manager.relay_command(user_id, {
                    "id": cmd_id,
                    "sender_device": trusted_devices[0]["device_id"],
                    "target_device": target_dev["device_id"],
                    "type": "open_app",
                    "payload": {"app": app_clean},
                    "created_at": time.time(),
                    "expiry": 60
                })
                reply = f"🌸 Done! Opened {app_clean.capitalize()} on your {target_dev['name']}."
            else:
                reply = f"I'd love to open {app_clean.capitalize()}, but you don't have a paired companion device online to open it on! 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        if is_ring_intent or is_send_note_intent:
            all_user_devices = db.get_user_devices(user_id)
            trusted_devices = [d for d in all_user_devices if d.get("status") == "trusted"]
            pending_devices = [d for d in all_user_devices if d.get("status") == "pending"]

            if trusted_devices:
                wants_laptop = bool(re.search(r"\b(laptop|pc|desktop|windows|computer)\b", lower_m))
                target_dev = None
                if wants_laptop:
                    for d in trusted_devices:
                        if d.get("platform", "").lower() in ("windows", "desktop", "laptop"):
                            target_dev = d
                            break
                else:
                    for d in trusted_devices:
                        if d.get("platform", "").lower() in ("android", "mobile", "ios"):
                            target_dev = d
                            break
                if not target_dev:
                    target_dev = trusted_devices[-1] if len(trusted_devices) > 1 else trusted_devices[0]

                action_type = "ring_phone" if is_ring_intent else "send_note"
                cmd_id = f"cmd_ai_{int(time.time()*1000)}"
                cmd_data = {
                    "id": cmd_id,
                    "sender_device": trusted_devices[0]["device_id"],
                    "target_device": target_dev["device_id"],
                    "type": action_type,
                    "payload": {"text": user_msg, "source": "ai_assistant"},
                    "created_at": time.time(),
                    "expiry": 60
                }
                relay_res = await relay_manager.relay_command(user_id, cmd_data)
                db.save_message(user_id, "user", user_msg)
                action_desc = f"Ringing your '{target_dev['name']}' now! 🔔" if is_ring_intent else f"Sent note to your '{target_dev['name']}'! 💌"
                reply = f"🌸 {action_desc}"
                db.save_message(user_id, "assistant", reply)
                return JSONResponse({
                    "reply": reply,
                    "proposal": None,
                    "remote_command_result": relay_res
                })
            elif pending_devices:
                p_dev = pending_devices[0]
                action_word = "ring" if is_ring_intent else "send a note to"
                reply = (
                    f"I'd love to {action_word} your phone, but your '{p_dev['name']}' is still waiting to be approved in Settings! 🌸\n\n"
                    f"1. Check the 6-digit code shown on your phone screen.\n"
                    f"2. In Settings ⚙️ -> My Devices on your laptop, click the green '[🔑 Enter Code]' button next to '{p_dev['name']}'.\n"
                    f"3. Type the 6 digits to approve and trust the phone.\n\n"
                    f"Once it's trusted, ask me to {action_word} your phone again and it will work right away!"
                )
                db.save_message(user_id, "user", user_msg)
                db.save_message(user_id, "assistant", reply)
                return JSONResponse({"reply": reply, "proposal": None})
            else:
                action_word = "ring" if is_ring_intent else "send a note to"
                reply = (
                    f"I'd love to {action_word} your phone, but you don't have any devices paired yet! 🌸\n\n"
                    f"To pair your phone, open the SINBHA Android app, log in, then approve the pairing in Settings ⚙️ -> My Devices on your laptop."
                )
                db.save_message(user_id, "user", user_msg)
                db.save_message(user_id, "assistant", reply)
                return JSONResponse({"reply": reply, "proposal": None})

    # 7. Standard message flow: call SINBHA brain
    db.save_message(user_id, "user", user_msg)
    db.log_audit(user_id, "CHAT_MESSAGE", f"User sent: '{user_msg[:80]}...'")

    recent_history = db.get_recent_messages(user_id, limit=20)
    current_facts = db.get_all_facts(user_id)

    # 7b. Web Search check (Step 15)
    web_search_meta = None
    web_search_context = None
    web_search_setting = db.get_setting(user_id, "web_search_enabled", "true")

    if web_search_setting == "true":
        needs_search, s_query, d_url = await detect_search_intent_smart(user_msg, recent_history[:-1])
        if needs_search:
            # Handle contextual follow-up phrases like "search and tell me" or "check it"
            if s_query and len(s_query.split()) <= 4 and re.search(r"^(search|check|look\s*up|tell\s*me|yeah|yes)", s_query, re.IGNORECASE):
                for prev in reversed(recent_history[:-1]):
                    if prev.get("role") == "user":
                        prev_text = prev.get("content", "")
                        if len(prev_text) > 4 and not re.search(r"^(hi|hello|hey|yes|no|ok|okay)\b", prev_text, re.IGNORECASE):
                            s_query = f"{prev_text} {s_query}".strip()
                            break

            search_res = await execute_web_search(
                user_id=user_id,
                raw_query=s_query,
                direct_url=d_url,
                user_facts=current_facts,
                user_email=user.get("email")
            )
            if search_res.limit_reached:
                ai_reply = search_res.limit_message
                db.save_message(user_id, "assistant", ai_reply)
                db.log_audit(user_id, "SEARCH_LIMIT_REACHED", f"Search limit reached for user #{user_id}")
                return JSONResponse({
                    "reply": ai_reply,
                    "proposal": None,
                    "new_facts": [],
                    "web_search": {"searched": False, "limit_reached": True, "sources": []}
                })

            if search_res.searched:
                web_search_context = search_res.context_text
                web_search_meta = {
                    "searched": True,
                    "sources": search_res.sources,
                    "cached": search_res.cached
                }
            elif search_res.error == "missing_api_key":
                web_search_meta = {
                    "searched": False,
                    "error": "missing_api_key",
                    "sources": []
                }

    offset = payload.tz_offset_minutes if payload.tz_offset_minutes is not None else payload.tz_offset
    user_tz = payload.timezone or user.get("timezone") or db.get_setting(user_id, "timezone", None)
    
    # If tz was unset or defaulted to UTC but client is in India (-330 offset), automatically ground to Asia/Kolkata
    if offset == -330 and (not user_tz or user_tz == "UTC"):
        user_tz = "Asia/Kolkata"
    elif not user_tz:
        user_tz = "UTC"

    if payload.timezone:
        try:
            db.set_setting(user_id, "timezone", payload.timezone)
        except Exception:
            pass
    elif offset == -330:
        try:
            db.set_setting(user_id, "timezone", "Asia/Kolkata")
        except Exception:
            pass

    brain_result = await call_sinbha_brain(
        user_message=user_msg,
        chat_history=recent_history[:-1],
        remembered_facts=current_facts,
        web_search_context=web_search_context,
        user_timezone=user_tz
    )
    ai_reply = brain_result.get("reply", "I'm right here with you 🌸")

    # 8. Check if AI proposed a structured task
    task_proposal_obj = None
    raw_prop = brain_result.get("raw_task_proposal")
    if raw_prop and isinstance(raw_prop, dict) and raw_prop.get("title"):
        title = str(raw_prop.get("title", "")).strip()
        raw_due = raw_prop.get("due_date")
        notes = raw_prop.get("notes")

        if len(title) >= 3 and title.lower() not in ("none", "task", "null"):
            try:
                import zoneinfo
                tz_obj = zoneinfo.ZoneInfo(user_tz)
                client_now = datetime.datetime.now(tz_obj)
            except Exception:
                client_now = datetime.datetime.now()
                if payload.tz_offset_minutes is not None:
                    utc_now = datetime.datetime.now(datetime.timezone.utc)
                    client_now = (utc_now - datetime.timedelta(minutes=payload.tz_offset_minutes)).replace(tzinfo=None)

            dt_res = parse_relative_datetime(raw_due, base_dt=client_now, user_timezone=user_tz)
            
            if dt_res.get("is_past") and dt_res.get("past_message"):
                if dt_res["past_message"] not in ai_reply:
                    ai_reply += "\n\n" + dt_res["past_message"]

            if dt_res.get("is_ambiguous"):
                real_due = dt_res["due_date"]
                due_time = None
                due_datetime = None
                display_due = dt_res["display"]
                suggested_rems = dt_res.get("suggested_reminders", [])
            else:
                real_due = dt_res["due_date"]
                due_time = dt_res["due_time"]
                due_datetime = dt_res["due_datetime"]
                display_due = dt_res["display"]
                suggested_rems = dt_res["suggested_reminders"]

                if not dt_res["time_specified"] and real_due:
                    if "what time" not in ai_reply.lower() and "time" not in ai_reply.lower():
                        ai_reply += "\n\nWhat time are you aiming to get it done by? (I can also set a reminder whenever you like) 🌸"

            prop_id = db.set_pending_proposal(
                user_id=user_id,
                title=title,
                due_date=real_due,
                notes=notes,
                due_time=due_time,
                due_datetime=due_datetime,
                suggested_reminders=suggested_rems
            )
            task_proposal_obj = {
                "type": "task_proposal",
                "id": prop_id,
                "title": title,
                "due_date": real_due,
                "due_time": due_time,
                "due_datetime": due_datetime,
                "display_due": display_due,
                "time_specified": dt_res["time_specified"],
                "is_ambiguous": dt_res.get("is_ambiguous", False),
                "ambiguous_options": dt_res.get("ambiguous_options", []),
                "suggested_reminders": suggested_rems,
                "notes": notes
            }

    db.save_message(user_id, "assistant", ai_reply)

    # 9. Background fact extraction (suppressed on untrusted external links)
    new_facts_saved = []
    if not (web_search_meta and web_search_meta.get("searched") and bool(re.search(r"https?://", user_msg))):
        try:
            extracted = await extract_explicit_facts(user_msg)
            for f in extracted:
                res = db.update_or_add_fact(user_id, f)
                if res.get("action") in ("added", "updated"):
                    new_facts_saved.append(f)
        except Exception as e:
            print(f"Fact extraction note: {e}")

    return JSONResponse({
        "reply": ai_reply,
        "proposal": task_proposal_obj,
        "new_facts": new_facts_saved,
        "web_search": web_search_meta
    })

# ----------------- Task Management Endpoints (Per-User) -----------------

@app.get("/api/tasks")
async def get_tasks_endpoint(user: dict = Depends(get_current_user)):
    """Returns all tasks for the logged-in user."""
    user_id = user["id"]
    tasks = db.get_all_tasks(user_id)
    pending_count = db.get_pending_tasks_count(user_id)
    return {"tasks": tasks, "pending_count": pending_count}

@app.patch("/api/tasks/{task_id}")
async def update_task_status_endpoint(task_id: int, payload: TaskStatusUpdateRequest, user: dict = Depends(get_reminder_action_user)):
    """
    Updates task status for the logged-in user.
    Requirement 3: Device tokens are restricted strictly to status: completed (Done).
    """
    user_id = user["id"]
    new_status = payload.status.strip().lower()
    if new_status not in ("pending", "completed"):
        raise HTTPException(status_code=400, detail="Status must be 'pending' or 'completed'")

    if user.get("is_device_token") and new_status != "completed":
        raise HTTPException(
            status_code=403,
            detail="Device token permissions are restricted strictly to marking tasks as completed (Done)."
        )

    ok = db.update_task_status(user_id, task_id, new_status)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "success": True,
        "task": db.get_task_by_id(user_id, task_id),
        "pending_count": db.get_pending_tasks_count(user_id)
    }

@app.delete("/api/tasks/{task_id}")
async def delete_task_endpoint(task_id: int, user: dict = Depends(get_current_user)):
    """Deletes a task belonging to the logged-in user."""
    user_id = user["id"]
    ok = db.delete_task(user_id, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "success": True,
        "pending_count": db.get_pending_tasks_count(user_id)
    }

@app.post("/api/tasks/confirm")
async def confirm_task_endpoint(payload: TaskConfirmWithRemindersRequest = None, user: dict = Depends(get_current_user)):
    """Confirms pending task proposal for the logged-in user."""
    user_id = user["id"]
    reminders = payload.reminders if payload and payload.reminders is not None else []
    chosen_time = payload.chosen_time if payload else None
    confirmed = db.confirm_pending_proposal(user_id, chosen_reminders=reminders, chosen_time=chosen_time)
    if not confirmed:
        return JSONResponse({
            "success": False,
            "reply": "This task proposal has expired or was already resolved 🌸"
        })

    reply_msg = f"Saved! I've added '{confirmed['title']}' to your tasks. You've got this! 🌸"
    db.save_message(user_id, "assistant", reply_msg)
    return JSONResponse({
        "success": True,
        "reply": reply_msg,
        "task": confirmed,
        "pending_count": db.get_pending_tasks_count(user_id)
    })

@app.post("/api/tasks/cancel")
async def cancel_task_endpoint(user: dict = Depends(get_current_user)):
    """Cancels pending task proposal for the logged-in user."""
    user_id = user["id"]
    db.cancel_pending_proposal(user_id, reason="User clicked Cancel")
    reply_msg = "No problem at all! I dropped that task proposal 🌸"
    db.save_message(user_id, "assistant", reply_msg)
    return JSONResponse({
        "success": True,
        "reply": reply_msg
    })

# ----------------- Reminder & Bird Flight Endpoints (Per-User) -----------------

@app.get("/api/reminders/check")
async def check_reminders_endpoint(tz_offset_minutes: Optional[int] = None, user: dict = Depends(get_reminder_action_user)):
    """Returns tasks that need attention right now for the logged-in user."""
    user_id = user["id"]
    if db.get_emergency_stopped(user_id):
        return {"reminder_needed": False, "task": None, "needing_bird": [], "count": 0, "emergency_stopped": True}

    now_dt = datetime.datetime.now()
    if tz_offset_minutes is not None:
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        client_now = utc_now - datetime.timedelta(minutes=tz_offset_minutes)
        now_dt = client_now.replace(tzinfo=None)

    needing = db.check_due_reminders(user_id, now_dt)
    if needing:
        first = needing[0]
        return {
            "reminder_needed": True,
            "task": first["task"],
            "reminder_id": first.get("reminder_id"),
            "is_explicit": first.get("is_explicit", False),
            "needing_bird": needing,
            "count": len(needing),
            "emergency_stopped": False
        }
    return {
        "reminder_needed": False,
        "task": None,
        "needing_bird": [],
        "count": 0,
        "emergency_stopped": False
    }

@app.post("/api/reminders/fired")
async def reminder_fired_endpoint(payload: ReminderFiredRequest, user: dict = Depends(get_reminder_action_user)):
    """Marks a reminder as fired for the logged-in user."""
    ok = db.mark_reminder_fired(user["id"], payload.task_id, payload.reminder_id)
    return {"success": ok}

@app.post("/api/reminders/snooze")
async def reminder_snooze_endpoint(payload: ReminderSnoozeRequest, user: dict = Depends(get_reminder_action_user)):
    """Snoozes a task's reminder for the logged-in user."""
    ok = db.snooze_task(user["id"], payload.task_id, payload.minutes)
    return {"success": ok}

@app.get("/api/reminders/upcoming")
async def get_upcoming_reminders_endpoint(user: dict = Depends(get_reminder_action_user)):
    """Returns upcoming pending reminders for native Android exact alarm scheduling."""
    user_id = user["id"]
    emergency_stopped = db.get_emergency_stopped(user_id)
    settings = db.get_all_settings(user_id)
    if emergency_stopped:
        return {
            "reminders": [],
            "emergency_stopped": True,
            "settings": settings
        }

    pending_tasks = [t for t in db.get_all_tasks(user_id) if t["status"] == "pending"]
    reminders_list = []
    for t in pending_tasks:
        snooze_str = t.get("snoozed_until")
        if snooze_str:
            reminders_list.append({
                "task_id": t["id"],
                "task_title": t["title"],
                "reminder_id": f"snooze_{t['id']}",
                "time": snooze_str,
                "label": f"Snoozed: {t['title']}",
                "is_explicit": True
            })
        for r in (t.get("reminders") or []):
            r_id = r.get("id")
            r_time = r.get("time")
            fired_ids = set(t.get("fired_reminders") or [])
            if r_id and r_id not in fired_ids and r_time:
                reminders_list.append({
                    "task_id": t["id"],
                    "task_title": t["title"],
                    "reminder_id": r_id,
                    "time": r_time,
                    "label": r.get("label", f"Reminder: {t['title']}"),
                    "is_explicit": True
                })
        due_d = t.get("due_date")
        due_t = t.get("due_time")
        if due_d and not (t.get("reminders") or []):
            reminders_list.append({
                "task_id": t["id"],
                "task_title": t["title"],
                "reminder_id": None,
                "time": f"{due_d} {due_t if due_t else '09:00'}",
                "label": f"Due: {t['title']}",
                "is_explicit": False
            })

    return {
        "reminders": reminders_list,
        "emergency_stopped": False,
        "settings": settings
    }

# ----------------- Mobile Device Token Management (Requirement 3) -----------------

@app.post("/api/auth/device-token")
@app.get("/api/auth/device-token")
async def issue_device_token_endpoint(request: Request, user: dict = Depends(get_current_user)):
    """
    Requirement 1 & 2: Issues or renews a dedicated device token for this device.
    Per-device token: Each device holds its own token.
    Rolling expiry: Automatically extended while the app is active.
    """
    existing_token = None
    device_name = "Android Companion"
    try:
        body = await request.json()
        if isinstance(body, dict):
            existing_token = body.get("device_token") or body.get("existing_token")
            device_name = body.get("device_name", device_name)
    except Exception:
        pass

    if not existing_token:
        existing_token = request.headers.get("x-device-token")

    # If an existing valid token is passed, renew it (rolling expiry)
    if existing_token:
        renewed = db.renew_device_token(existing_token, days=30)
        if renewed:
            return {
                "success": True,
                "device_token": renewed["device_token"],
                "scope": "reminders_only",
                "expires_at": renewed["expires_at"],
                "user_id": user["id"],
                "email": user["email"],
                "emergency_stopped": user.get("emergency_stopped", False),
                "renewed": True
            }

    dev_data = db.create_device_token(user["id"], device_name=device_name, days_valid=30)
    return {
        "success": True,
        "device_token": dev_data["device_token"],
        "scope": dev_data["scope"],
        "expires_at": dev_data["expires_at"],
        "user_id": user["id"],
        "email": user["email"],
        "emergency_stopped": user.get("emergency_stopped", False),
        "renewed": False
    }

@app.post("/api/auth/device-token/renew")
async def renew_device_token_endpoint(request: Request):
    """
    Requirement 2: Dedicated endpoint to renew rolling expiry of a device token during active use.
    """
    dev_token = request.headers.get("x-device-token")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer snb_dev_"):
        dev_token = auth_header.replace("Bearer ", "").strip()
    if not dev_token:
        try:
            body = await request.json()
            if isinstance(body, dict):
                dev_token = body.get("device_token")
        except Exception:
            pass

    if not dev_token:
        raise HTTPException(status_code=400, detail="Device token required")

    renewed = db.renew_device_token(dev_token, days=30)
    if not renewed:
        raise HTTPException(status_code=401, detail="Device token is invalid or expired")

    return {
        "success": True,
        "device_token": renewed["device_token"],
        "expires_at": renewed["expires_at"],
        "message": "Device token renewed successfully"
    }

@app.post("/api/auth/device-token/revoke")
async def revoke_device_tokens_endpoint(request: Request, user: dict = Depends(get_current_user)):
    """Revokes a specific device token, or all tokens for this user if no specific token given."""
    dev_token = request.headers.get("x-device-token")
    try:
        body = await request.json()
        if isinstance(body, dict):
            dev_token = body.get("device_token", dev_token)
    except Exception:
        pass

    if dev_token:
        db.revoke_device_token(dev_token)
        return {"success": True, "message": "Specific device token revoked."}

    db.revoke_user_device_tokens(user["id"])
    return {"success": True, "message": "All mobile companion device tokens revoked."}

# ----------------- App Version Gate & Lockout Guard (Requirement 1 & 4) -----------------

def is_semver_higher(v1: str, v2: str) -> bool:
    """Helper to compare semantic version numbers."""
    try:
        parts1 = [int(x) for x in re.sub(r"[^\d.]", "", str(v1)).split(".") if x]
        parts2 = [int(x) for x in re.sub(r"[^\d.]", "", str(v2)).split(".") if x]
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))
        return parts1 > parts2
    except Exception:
        return False

@app.get("/api/app/version-check")
async def app_version_check_endpoint():
    """
    Requirement 1: Links point to public sinbha-releases repository.
    Requirement 4: Accidental lockout prevention. If minimum version is higher
    than the latest published version, ignores it, clamps to latest, and logs a warning.
    """
    # Read current package.json version dynamically as fallback
    pkg_version = "1.0.4"
    pkg_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "package.json")
    if os.path.exists(pkg_file):
        try:
            with open(pkg_file, "r", encoding="utf-8") as f:
                pkg_version = json.load(f).get("version", "1.0.4")
        except Exception:
            pass

    min_android = os.getenv("MIN_APP_VERSION_ANDROID", "1.0.0")
    latest_android = os.getenv("LATEST_APP_VERSION_ANDROID", "1.1.0")
    min_desktop = os.getenv("MIN_APP_VERSION_DESKTOP", "1.0.0")
    latest_desktop = os.getenv("LATEST_APP_VERSION_DESKTOP", "1.1.0")

    # Safety clamp: min_version must never exceed latest_version
    if is_semver_higher(min_android, latest_android):
        print(f"⚠️ [WARNING] Config error prevented: MIN_APP_VERSION_ANDROID ({min_android}) was higher than LATEST_APP_VERSION_ANDROID ({latest_android}). Clamping to latest to prevent accidental user lockout.")
        min_android = latest_android

    if is_semver_higher(min_desktop, latest_desktop):
        print(f"⚠️ [WARNING] Config error prevented: MIN_APP_VERSION_DESKTOP ({min_desktop}) was higher than LATEST_APP_VERSION_DESKTOP ({latest_desktop}). Clamping to latest to prevent accidental user lockout.")
        min_desktop = latest_desktop

    default_dl_android = f"https://github.com/kbtteja456-KBT/sinbha-releases/releases/download/android-v{latest_android}/SINBHA.apk"
    default_dl_desktop = f"https://github.com/kbtteja456-KBT/sinbha-releases/releases/download/windows-v{latest_desktop}/SINBHA-Setup.exe"
    download_android = os.getenv("DOWNLOAD_URL_ANDROID", default_dl_android)
    download_desktop = os.getenv("DOWNLOAD_URL_DESKTOP", default_dl_desktop)

    return {
        "min_version_android": min_android,
        "latest_version_android": latest_android,
        "min_version_desktop": min_desktop,
        "latest_version_desktop": latest_desktop,
        "download_url_android": download_android,
        "download_url_desktop": download_desktop,
        "releases_repo": "https://github.com/kbtteja456-KBT/sinbha-releases",
        "message": "A newer version of SINBHA is available. Please update to continue enjoying your companion."
    }

@app.post("/api/devices/notifications/sync")
async def sync_device_notifications(request: Request):
    """Syncs recent notification buffer from phone."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = db.get_user_by_session(token) if token else None
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        notifs = body.get("notifications", [])
        relay_manager.store_user_notifications(user["id"], notifs)
        return {"success": True, "count": len(notifs)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.get("/api/devices/notifications")
async def get_device_notifications(request: Request):
    """Retrieves recent notifications collected across paired devices."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = db.get_user_by_session(token) if token else None
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    notifs = relay_manager.get_user_notifications(user["id"])
    return {"notifications": notifs}


@app.get("/api/settings")
async def get_settings_endpoint(user: dict = Depends(get_current_user)):
    """Returns settings for the logged-in user."""
    return {"settings": db.get_all_settings(user["id"])}

@app.post("/api/settings")
async def update_settings_endpoint(payload: SettingsUpdateRequest, user: dict = Depends(get_current_user)):
    """Updates settings for the logged-in user."""
    user_id = user["id"]
    db.set_setting(user_id, "persistence", payload.persistence)
    db.set_setting(user_id, "quiet_hours_enabled", payload.quiet_hours_enabled)
    db.set_setting(user_id, "quiet_hours_start", payload.quiet_hours_start)
    db.set_setting(user_id, "quiet_hours_end", payload.quiet_hours_end)
    if payload.country:
        db.set_setting(user_id, "country", payload.country)
    if payload.timezone:
        db.set_setting(user_id, "timezone", payload.timezone)
    if payload.web_search_enabled is not None:
        db.set_setting(user_id, "web_search_enabled", payload.web_search_enabled)
    db.log_audit(user_id, "SETTINGS_UPDATED", f"Persistence: {payload.persistence}, Quiet hours: {payload.quiet_hours_start}-{payload.quiet_hours_end}, Web Search: {payload.web_search_enabled}")
    return {"success": True, "settings": db.get_all_settings(user_id)}

@app.post("/api/confirm-action")
async def confirm_action_endpoint(payload: ActionConfirmRequest, user: dict = Depends(get_current_user)):
    """Handles action confirmation for the logged-in user."""
    user_id = user["id"]
    action = payload.action.strip().lower()

    pending_task_act = db.get_pending_task_action(user_id)
    if pending_task_act:
        if action == "confirm":
            res = db.confirm_pending_task_action(user_id)
            if res:
                reply = f"Woohoo! 🎉 Marked '{res['task_title']}' as completed! Amazing job! 🌸" if res["action_type"] == "task_complete" else f"I've removed '{res['task_title']}' from your tasks 🌸"
                db.save_message(user_id, "assistant", reply)
                return JSONResponse({
                    "success": True,
                    "reply": reply,
                    "action_performed": res["action_type"],
                    "task_id": res["task_id"],
                    "pending_count": db.get_pending_tasks_count(user_id)
                })
        else:
            db.cancel_pending_task_action(user_id, reason="User clicked Cancel")
            reply = "No problem at all! Kept it just as it is 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({"success": True, "reply": reply, "action_performed": "cancelled"})

    pending = db.get_pending_action(user_id)
    if not pending:
        return JSONResponse({"success": False, "reply": "No pending action found 🌸"})

    if action == "confirm":
        if pending["action_type"] == "forget_fact":
            target_id = pending["target_id"]
            db.delete_fact(user_id, target_id)
            db.clear_pending_action(user_id)
            reply = "I've forgotten that for you! It's wiped from my memory 🌸"
            db.save_message(user_id, "assistant", reply)
            return JSONResponse({
                "success": True,
                "reply": reply,
                "action_performed": "fact_deleted",
                "deleted_fact_id": target_id
            })
    else:
        db.clear_pending_action(user_id)
        reply = "No problem at all! I'll keep remembering it 🌸"
        db.save_message(user_id, "assistant", reply)
        return JSONResponse({"success": True, "reply": reply, "action_performed": "cancelled"})

    db.clear_pending_action(user_id)
    return JSONResponse({"success": True, "reply": "Action completed 🌸"})

# ----------------- Emergency STOP / Resume Endpoints (Per-User) -----------------

@app.post("/api/stop")
async def stop_endpoint(user: dict = Depends(get_current_user)):
    """Per-user emergency stop switch."""
    user_id = user["id"]
    db.set_emergency_stopped(user_id, True)
    relay_manager.on_emergency_stop(user_id)
    db.cancel_pending_proposal(user_id, reason="Emergency STOP button clicked in header")
    db.cancel_pending_task_action(user_id, reason="Emergency STOP button clicked in header")
    db.log_audit(user_id, "STOP_TRIGGERED", "Emergency STOP button clicked in header.")
    
    return JSONResponse({
        "status": "stopped",
        "message": "🛑 Emergency STOP triggered. All processing halted immediately."
    })

@app.post("/api/resume")
async def resume_endpoint(user: dict = Depends(get_current_user)):
    """Resumes companion for this user."""
    user_id = user["id"]
    db.set_emergency_stopped(user_id, False)
    db.log_audit(user_id, "STOP_RESUMED", "Resume button clicked.")
    return JSONResponse({
        "status": "resumed",
        "message": "🌸 Welcome back! Everything is quiet and ready."
    })

# ----------------- Memory & Admin/Dev Endpoints (Requirement 4) -----------------

@app.get("/api/facts")
async def get_facts_endpoint(user: dict = Depends(get_current_user)):
    """Returns remembered facts for the logged-in user."""
    return {"facts": db.get_all_facts(user["id"])}

@app.post("/api/facts")
async def add_fact_endpoint(payload: FactCreateRequest, user: dict = Depends(get_current_user)):
    """Manually add a fact to memory for the logged-in user."""
    new_id = db.add_fact(user["id"], payload.fact, payload.category or "general")
    if not new_id:
        raise HTTPException(status_code=400, detail="Fact cannot be empty.")
    return {"success": True, "id": new_id}

@app.put("/api/facts/{fact_id}")
async def update_fact_endpoint(fact_id: int, payload: FactUpdateRequest, user: dict = Depends(get_current_user)):
    """Edit an existing fact for the logged-in user."""
    ok = db.update_fact(user["id"], fact_id, payload.fact)
    if not ok:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"success": True}

@app.delete("/api/facts/{fact_id}")
async def delete_fact_endpoint(fact_id: int, user: dict = Depends(get_current_user)):
    """Delete a fact for the logged-in user."""
    ok = db.delete_fact(user["id"], fact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"success": True}

@app.post("/api/purge")
async def purge_data_endpoint(user: dict = Depends(get_current_user)):
    """Wipes all data (messages, facts, tasks) for the logged-in user."""
    db.purge_all_data(user["id"])
    return {"success": True, "message": "All your messages, facts, and tasks have been wiped cleanly."}

@app.get("/api/dev/facts")
async def dev_facts_endpoint(user: dict = Depends(get_current_user)):
    """
    Requirement 4: Dev endpoints work only when DEV_MODE=true AND logged in as an admin.
    """
    if not user.get("is_admin") or not is_dev_mode_active():
        raise HTTPException(status_code=403, detail="Developer access denied. Requires admin user and DEV_MODE=true.")
    return {
        "dev_mode": True,
        "facts": db.get_all_facts(user["id"]),
        "audit_logs": db.get_audit_logs(user["id"], limit=25)
    }

@app.get("/api/audit")
async def get_audit_endpoint(user: dict = Depends(get_current_user)):
    """
    Requirement 4: Audit log endpoint works only when DEV_MODE=true AND logged in as an admin.
    """
    if not user.get("is_admin") or not is_dev_mode_active():
        raise HTTPException(status_code=403, detail="Access denied. Audit logs require admin privileges and DEV_MODE=true.")
    return {"logs": db.get_audit_logs(user["id"], limit=50)}

# ----------------- Step 16: Device Pairing & Secure Command Channel -----------------

@app.post("/api/devices/register")
async def register_device_endpoint(payload: DeviceRegisterRequest, user: dict = Depends(get_current_user)):
    """
    Registers or handshakes a device for the logged-in user.
    - New accounts may trust their first device at signup.
    - For existing accounts, first device must not become trusted automatically; requires password verification.
    - Subsequent new devices start in 'pending' status with a 5-minute one-time pairing code.
    - Broadcasts pairing_requested event to connected trusted devices if pending.
    """
    try:
        device = db.create_or_register_device(
            user_id=user["id"],
            device_id=payload.device_id.strip(),
            name=payload.name or "Web Companion",
            platform=payload.platform or "web",
            password=payload.password,
            is_signup=payload.is_signup or False,
        )
        if device.get("status") == "pending":
            await relay_manager.notify_pairing_requested(user["id"], device)
        return {"success": True, "device": device}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register device: {e}")

@app.get("/api/devices")
async def list_devices_endpoint(user: dict = Depends(get_current_user)):
    """Lists all registered devices for the user."""
    devices = db.get_user_devices(user["id"])
    return {"devices": devices}

@app.get("/api/devices/status")
async def get_device_status_endpoint(device_id: str, user: dict = Depends(get_current_user)):
    """Checks pairing and trust status for a specific device."""
    dev = db.get_device_by_id(user["id"], device_id.strip())
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found.")
    trusted_count = len([d for d in db.get_user_devices(user["id"]) if d["status"] == "trusted"])
    dev["requires_first_device_trust"] = (trusted_count == 0 and dev.get("status") == "pending")
    return {"device": dev}

@app.post("/api/devices/approve-pairing")
async def approve_pairing_endpoint(payload: DevicePairApproveRequest, user: dict = Depends(get_current_user)):
    """
    Approves a pending device from an already trusted device using its 5-minute one-time code.
    """
    res = db.approve_device_pairing(
        user_id=user["id"],
        code_or_target_id=payload.code,
        approver_device_id=payload.approver_device_id
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Pairing approval failed."))
    return res

@app.post("/api/devices/refresh-code")
async def refresh_pairing_code_endpoint(device_id: str, user: dict = Depends(get_current_user)):
    """Regenerates a fresh 5-minute code for a pending device."""
    try:
        dev = db.regenerate_pairing_code(user["id"], device_id.strip())
        return {"success": True, "device": dev}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/devices/{device_id}")
async def update_device_endpoint(device_id: str, payload: DeviceUpdateRequest, user: dict = Depends(get_current_user)):
    """Renames device, adjusts permission level (0-4), or toggles capabilities."""
    clean_id = device_id.strip()
    updated = None
    try:
        if payload.name:
            updated = db.rename_device(user["id"], clean_id, payload.name)
        if payload.permission_level is not None or payload.capabilities is not None:
            updated = db.update_device_permissions(
                user["id"],
                clean_id,
                permission_level=payload.permission_level,
                capabilities=payload.capabilities,
                password=payload.password,
            )
        if not updated:
            updated = db.get_device_by_id(user["id"], clean_id)
            if not updated:
                raise HTTPException(status_code=404, detail="Device not found.")
        return {"success": True, "device": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update device: {e}")

@app.delete("/api/devices/{device_id}")
async def revoke_device_endpoint(device_id: str, user: dict = Depends(get_current_user)):
    """Immediately revokes access for a device."""
    clean_id = device_id.strip()
    try:
        revoked = db.revoke_device(user["id"], clean_id)
        relay_manager.unregister_websocket(user["id"], clean_id)
        return {"success": True, "message": f"Device '{revoked['name']}' revoked immediately.", "device": revoked}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/devices/disconnect-all")
async def disconnect_all_devices_endpoint(user: dict = Depends(get_current_user)):
    """
    Halts and disconnects all devices immediately without asking the AI.
    Revokes access, clears command queues, and closes channels.
    """
    count = db.disconnect_all_devices(user["id"])
    relay_manager.on_disconnect_all(user["id"])
    return {
        "success": True,
        "revoked_count": count,
        "message": "All devices disconnected and revoked immediately."
    }

@app.post("/api/devices/commands/send")
async def send_device_command_endpoint(payload: DeviceCommandRequest, user: dict = Depends(get_current_user)):
    """
    Sends a secure command to another device.
    Enforces replay protection, 60s expiry, per-user rate limits, STOP check, and permission gates.
    Audit log records metadata only, never the payload content.
    """
    res = await relay_manager.relay_command(
        user_id=user["id"],
        cmd_data=payload.model_dump()
    )
    if not res.get("success"):
        err = res.get("error", "FAILED")
        msg = res.get("message", "Failed to relay command.")
        raise HTTPException(status_code=400, detail=f"{err}: {msg}")
    return res

@app.get("/api/devices/commands/pending")
async def get_pending_commands_endpoint(device_id: str, user: dict = Depends(get_current_user)):
    """
    Retrieves and drains pending offline commands for a device.
    Stale commands (> 60s) are pruned and never returned.
    """
    clean_id = device_id.strip()
    dev = db.get_device_by_id(user["id"], clean_id)
    if not dev or dev["status"] != "trusted":
        raise HTTPException(status_code=403, detail="Device is not trusted or does not belong to you.")

    commands = relay_manager.get_pending_offline_commands(user["id"], clean_id)
    return {"commands": commands}

@app.post("/api/devices/commands/{command_id}/ack")
async def ack_device_command_endpoint(command_id: str, payload: DeviceCommandAckRequest, user: dict = Depends(get_current_user)):
    """Acknowledges receipt or execution outcome of a command."""
    db.log_audit(
        user["id"],
        "DEVICE_COMMAND_ACK",
        json.dumps({"command_id": command_id, "status": payload.status, "result": "acknowledged"})
    )
    return {"success": True, "command_id": command_id, "status": payload.status}

@app.websocket("/api/ws/devices")
async def device_websocket_endpoint(websocket: WebSocket):
    """
    Authenticated WebSocket relay channel for real-time remote commands.
    """
    await websocket.accept()
    user_id = None
    device_id = None
    try:
        token = websocket.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            token = websocket.query_params.get("token")
        q_dev_id = websocket.query_params.get("device_id")

        if not token or not q_dev_id:
            init_msg = await websocket.receive_text()
            data = json.loads(init_msg)
            if data.get("type") == "auth":
                token = data.get("token") or token
                q_dev_id = data.get("device_id") or q_dev_id

        if not token:
            await websocket.send_text(json.dumps({"type": "error", "message": "Authentication required."}))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user = db.get_user_by_session(token)
        if not user:
            await websocket.send_text(json.dumps({"type": "error", "message": "Invalid session token."}))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user_id = user["id"]
        device_id = q_dev_id.strip() if q_dev_id else "unknown"

        if db.get_emergency_stopped(user_id):
            await websocket.send_text(json.dumps({
                "type": "emergency_stop",
                "message": "Emergency STOP active. Remote commands suspended."
            }))

        dev = db.get_device_by_id(user_id, device_id)
        if not dev or dev["status"] != "trusted":
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Device is not trusted (status: {dev['status'] if dev else 'unregistered'})."
            }))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        relay_manager.register_websocket(user_id, device_id, websocket)
        await websocket.send_text(json.dumps({
            "type": "ready",
            "device_id": device_id,
            "message": "Secure channel connected 🌸"
        }))

        # Drain and deliver unexpired offline commands
        pending_cmds = relay_manager.get_pending_offline_commands(user_id, device_id)
        for pcmd in pending_cmds:
            await websocket.send_text(json.dumps(pcmd))

        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
            except Exception:
                continue

            msg_type = msg.get("type")
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "time": time.time()}))
            elif msg_type == "send_command":
                cmd_data = msg.get("command") or {}
                result = await relay_manager.relay_command(user_id, cmd_data)
                await websocket.send_text(json.dumps({
                    "type": "command_result",
                    "id": cmd_data.get("id"),
                    "result": result
                }))
            elif msg_type == "ack":
                cid = msg.get("id")
                st = msg.get("status", "executed")
                db.log_audit(
                    user_id,
                    "DEVICE_COMMAND_ACK",
                    json.dumps({"command_id": cid, "status": st, "result": "acknowledged"})
                )
            elif msg_type == "device_status":
                relay_manager.store_device_telemetry(user_id, device_id, {
                    "battery": msg.get("battery"),
                    "is_charging": msg.get("is_charging", False),
                    "platform": msg.get("platform", "unknown"),
                    "updated_at": time.time()
                })
            elif msg_type == "sync_notifications":
                notifs = msg.get("notifications") or []
                relay_manager.store_user_notifications(user_id, notifs)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if user_id and device_id:
            relay_manager.unregister_websocket(user_id, device_id, websocket)

# ----------------- Host Info & Static Files -----------------


@app.get("/api/info")
async def info_endpoint(request: Request):
    """Provides general host information and session state."""
    port = int(os.environ.get("PORT", 8080))
    creds = get_llm_credentials()
    model = creds["model"] if creds else os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    user = await get_current_user_optional(request)
    is_stopped = db.get_emergency_stopped(user["id"]) if user else False

    return {
        "companion": "SINBHA",
        "local_ip": get_local_ip(),
        "port": port,
        "model": model,
        "dev_mode": is_dev_mode_active(),
        "logged_in": bool(user),
        "user": user,
        "emergency_stopped": is_stopped
    }

@app.get("/api/health")
async def health_check():
    """
    Requirement 2 & 7: Production health check and monitoring endpoint.
    Used by Render zero-downtime deploys and 15-minute keep-alive cron jobs.
    """
    db_connected = False
    try:
        with db.get_db_session() as session:
            session.execute(db.select(1))
            db_connected = True
    except Exception:
        db_connected = False

    global_ai_count = db.get_global_today_message_count()
    global_ai_cap = get_daily_global_ai_limit()
    ai_cap_reached = global_ai_count >= global_ai_cap

    status_code = 200 if db_connected else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_connected else "unhealthy",
            "environment": os.getenv("ENV", "development"),
            "database": "connected" if db_connected else "disconnected",
            "uptime_seconds": int(time.time() - APP_START_TIME),
            "ai_cost_cap_reached": ai_cap_reached,
            "ai_today_messages": global_ai_count,
            "ai_daily_cap": global_ai_cap,
            "version": "1.0.0"
        }
    )

# ----------------- Web Intelligence Agent Subsystem Endpoint -----------------

@app.post("/api/v1/research/search", response_model=ResearchSearchResponse)
async def research_search_endpoint(payload: ResearchSearchRequest, user: dict = Depends(get_current_user)):
    """
    Dedicated Master Web Intelligence Agent Endpoint.
    Performs autonomous search decision, multi-provider search, safe reading,
    claim verification, and citation validation.
    """
    res = await agent_instance.research_and_answer(
        question=payload.question,
        depth=payload.research_depth or "normal",
        user_timezone=user.get("timezone") or "UTC"
    )
    db.log_audit(user["id"], "WEB_RESEARCH_COMPLETED", f"Query: {payload.question[:60]}... (Sources: {len(res.sources)})")
    return res

# Serve static UI files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse(
        "static/index.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

if __name__ == "__main__":
    import uvicorn
    import sys
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    port = int(os.environ.get("PORT", 8080))
    local_ip = get_local_ip()
    print("=" * 60)
    print("🌸 SINBHA is running!")
    print(f"👉 On your computer:  http://localhost:{port}")
    print(f"👉 On your phone:     http://{local_ip}:{port}")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
