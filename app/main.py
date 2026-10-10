import os
import socket
import re
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

# Load environment variables (.env)
load_dotenv()

from app.ai_brain import (
    call_sinbha_brain,
    extract_explicit_facts,
    detect_fact_correction,
    is_forget_intent,
    find_target_fact_to_forget,
    parse_relative_date,
)
from app import database as db

app = FastAPI(title="SINBHA - Personal AI Companion")

# Emergency stop state tracker
emergency_stop_triggered = False

class ChatRequest(BaseModel):
    message: str

class ActionConfirmRequest(BaseModel):
    action: str  # "confirm" or "cancel"

class TaskActionRequest(BaseModel):
    proposal_id: Optional[int] = None

class FactCreateRequest(BaseModel):
    fact: str
    category: Optional[str] = "general"

class FactUpdateRequest(BaseModel):
    fact: str

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

# ----------------- Chat & Message Endpoints -----------------

@app.get("/api/messages")
async def get_messages_endpoint():
    """Returns stored conversation history so UI restores on reload."""
    msgs = db.get_all_messages()
    return {"messages": msgs, "emergency_stopped": emergency_stop_triggered}

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    global emergency_stop_triggered
    user_msg = payload.message.strip()
    
    if not user_msg:
        return JSONResponse({
            "reply": "I'm listening whenever you want to talk 🌸",
            "proposal": None
        })
    
    # RULE 3 & 7: STOP check comes FIRST
    if user_msg.upper() == "STOP":
        emergency_stop_triggered = True
        db.save_message("user", user_msg)
        
        # Requirement 6: If STOP is triggered, cancel any pending proposal
        db.cancel_pending_proposal(reason="Emergency STOP command received in chat")
        
        stop_reply = "🛑 STOP command received. All operations halted immediately. Type any message or click 'Resume Chat' to continue whenever you're ready 🌸"
        db.save_message("assistant", stop_reply)
        db.log_audit("STOP_TRIGGERED", "User commanded STOP in chat.")
        return JSONResponse({
            "reply": stop_reply,
            "proposal": None,
            "stopped": True
        })

    # If stopped previously and user sends a normal message, automatically resume
    if emergency_stop_triggered:
        emergency_stop_triggered = False
        db.log_audit("STOP_RESUMED", "Chat resumed by normal message.")

    # 1. Check for pending task proposal confirmation in chat ("confirm", "yes", "save it" / "cancel", "no")
    pending_task = db.get_pending_proposal()
    if pending_task:
        lower_msg = user_msg.lower()
        is_task_confirm = bool(re.search(r"^(yes|yeah|yep|yup|confirm|sure|save\s+it|save\s+task|please\s+do|do\s+it|add\s+it)\b", lower_msg))
        is_task_cancel = bool(re.search(r"^(no|nope|cancel|don't\s+save|drop\s+it|nevermind|nah|mat\s+karo)\b", lower_msg))

        if is_task_confirm:
            confirmed = db.confirm_pending_proposal()
            if confirmed:
                db.save_message("user", user_msg)
                reply_msg = f"Saved! I've added '{confirmed['title']}' to your tasks. You've got this! 🌸"
                db.save_message("assistant", reply_msg)
                return JSONResponse({
                    "reply": reply_msg,
                    "proposal": None,
                    "task_confirmed": confirmed
                })
        elif is_task_cancel:
            db.cancel_pending_proposal(reason="User cancelled in chat")
            db.save_message("user", user_msg)
            reply_msg = "No problem at all! I dropped that task proposal 🌸"
            db.save_message("assistant", reply_msg)
            return JSONResponse({
                "reply": reply_msg,
                "proposal": None,
                "task_cancelled": True
            })

    # 2. Check for pending memory fact deletion confirmation
    pending_mem = db.get_pending_action()
    if pending_mem and pending_mem["action_type"] == "forget_fact":
        lower_msg = user_msg.lower()
        is_yes = bool(re.search(r"^(yes|yeah|yep|yup|sure|ok|okay|confirm|please|do it|forget it|delete it|ha|haan|yes please|definitely|go ahead)\b", lower_msg))
        is_no = bool(re.search(r"^(no|nope|cancel|don't|keep it|nevermind|nah|stop|mat karo)\b", lower_msg))

        if is_yes:
            target_id = pending_mem["target_id"]
            db.save_message("user", user_msg)
            db.delete_fact(target_id)  # Logs FACT_DELETED in audit_log
            db.clear_pending_action()
            reply = "I've forgotten that for you! It's wiped from my memory 🌸"
            db.save_message("assistant", reply)
            return JSONResponse({
                "reply": reply,
                "proposal": None,
                "action_performed": "fact_deleted",
                "deleted_fact_id": target_id
            })
        elif is_no:
            db.save_message("user", user_msg)
            db.clear_pending_action()
            reply = "No problem at all! I'll keep remembering it 🌸"
            db.save_message("assistant", reply)
            return JSONResponse({
                "reply": reply,
                "proposal": None,
                "action_performed": "cancelled"
            })
        else:
            db.clear_pending_action()

    # 3. Check for forget request ("forget X", "forget that", "forget my name")
    facts = db.get_all_facts()
    if is_forget_intent(user_msg):
        db.save_message("user", user_msg)
        if not facts:
            reply = "I don't have anything saved in my memory to forget right now! 🌸"
            db.save_message("assistant", reply)
            return JSONResponse({"reply": reply, "proposal": None})

        target_fact = find_target_fact_to_forget(user_msg, facts)
        db.set_pending_action("forget_fact", target_id=target_fact["id"], target_text=target_fact["fact"])
        
        reply = f"Are you sure you want me to forget that '{target_fact['fact']}'? Just reply \"yes\" or confirm to remove it 🌸"
        db.save_message("assistant", reply)
        return JSONResponse({
            "reply": reply,
            "proposal": {
                "type": "confirm_forget",
                "fact_id": target_fact["id"],
                "fact_text": target_fact["fact"],
                "prompt": f"Forget '{target_fact['fact']}'?"
            }
        })

    # 4. Check for fact correction ("my name is Ravi, not Rahul")
    target_id, updated_text, old_text = detect_fact_correction(user_msg, facts)
    if target_id and updated_text:
        db.save_message("user", user_msg)
        db.update_fact(target_id, updated_text)  # Logs FACT_UPDATED in audit_log
        
        updated_facts = db.get_all_facts()
        recent_history = db.get_recent_messages(limit=20)
        brain_result = await call_sinbha_brain(
            user_message=user_msg,
            chat_history=recent_history[:-1],
            remembered_facts=updated_facts
        )
        ai_reply = brain_result.get("reply", f"Got it! I've updated my memory: {updated_text} 🌸")
        db.save_message("assistant", ai_reply)
        return JSONResponse({
            "reply": ai_reply,
            "proposal": None,
            "updated_fact": {"id": target_id, "fact": updated_text}
        })

    # 5. Standard message flow: call SINBHA brain
    db.save_message("user", user_msg)
    db.log_audit("CHAT_MESSAGE", f"User sent: '{user_msg[:80]}...'")

    recent_history = db.get_recent_messages(limit=20)
    current_facts = db.get_all_facts()

    brain_result = await call_sinbha_brain(
        user_message=user_msg,
        chat_history=recent_history[:-1],
        remembered_facts=current_facts
    )
    ai_reply = brain_result.get("reply", "I'm right here with you 🌸")

    # 6. Step 5: Check if AI proposed a structured task
    task_proposal_obj = None
    raw_prop = brain_result.get("raw_task_proposal")
    if raw_prop and isinstance(raw_prop, dict) and raw_prop.get("title"):
        title = str(raw_prop.get("title", "")).strip()
        raw_due = raw_prop.get("due_date")
        notes = raw_prop.get("notes")

        # Validate title (App-level validation)
        if len(title) >= 3 and title.lower() not in ("none", "task", "null"):
            real_due, is_ambiguous = parse_relative_date(raw_due)
            
            if is_ambiguous:
                # If date was ambiguous (e.g. "sometime", "soon", "later"), ask instead of guessing
                if "when" not in ai_reply.lower() and "due" not in ai_reply.lower():
                    ai_reply += "\n\nWhen would you like to get this done by? Let me know so I can keep track of it accurately for you 🌸"
                real_due = None

            # Save proposal requiring user confirmation (expires after 30 mins)
            prop_id = db.set_pending_proposal(title=title, due_date=real_due, notes=notes)
            task_proposal_obj = {
                "type": "task_proposal",
                "id": prop_id,
                "title": title,
                "due_date": real_due,
                "notes": notes
            }

    db.save_message("assistant", ai_reply)

    # 7. Background fact extraction
    new_facts_saved = []
    try:
        extracted = await extract_explicit_facts(user_msg)
        for f in extracted:
            res = db.update_or_add_fact(f)
            if res.get("action") in ("added", "updated"):
                new_facts_saved.append(f)
    except Exception as e:
        print(f"Fact extraction note: {e}")

    return JSONResponse({
        "reply": ai_reply,
        "proposal": task_proposal_obj,
        "new_facts": new_facts_saved
    })

# ----------------- Task Proposal & Management Endpoints (Step 5) -----------------

@app.get("/api/tasks")
async def get_tasks_endpoint():
    """Returns all confirmed tasks for Tasks drawer."""
    return {"tasks": db.get_all_tasks()}

@app.post("/api/tasks/confirm")
async def confirm_task_endpoint(payload: TaskActionRequest = None):
    """Confirms the pending task proposal and saves it to tasks table."""
    confirmed = db.confirm_pending_proposal()
    if not confirmed:
        return JSONResponse({
            "success": False,
            "reply": "This task proposal has expired or was already resolved 🌸"
        })

    reply_msg = f"Saved! I've added '{confirmed['title']}' to your tasks. You've got this! 🌸"
    db.save_message("assistant", reply_msg)
    return JSONResponse({
        "success": True,
        "reply": reply_msg,
        "task": confirmed
    })

@app.post("/api/tasks/cancel")
async def cancel_task_endpoint(payload: TaskActionRequest = None):
    """Cancels the pending task proposal kindly without saving."""
    db.cancel_pending_proposal(reason="User clicked Cancel")
    reply_msg = "No problem at all! I dropped that task proposal 🌸"
    db.save_message("assistant", reply_msg)
    return JSONResponse({
        "success": True,
        "reply": reply_msg
    })

# Action confirmation endpoint (for clicking Confirm/Cancel on memory deletion)
@app.post("/api/confirm-action")
async def confirm_action_endpoint(payload: ActionConfirmRequest):
    """Handles memory confirmation (such as confirming deletion of a fact)."""
    action = payload.action.strip().lower()
    pending = db.get_pending_action()
    
    if not pending:
        return JSONResponse({"success": False, "reply": "No pending action found 🌸"})

    if action == "confirm":
        if pending["action_type"] == "forget_fact":
            target_id = pending["target_id"]
            db.delete_fact(target_id)  # Logs FACT_DELETED
            db.clear_pending_action()
            reply = "I've forgotten that for you! It's wiped from my memory 🌸"
            db.save_message("assistant", reply)
            return JSONResponse({
                "success": True,
                "reply": reply,
                "action_performed": "fact_deleted",
                "deleted_fact_id": target_id
            })
    else:
        db.clear_pending_action()
        reply = "No problem at all! I'll keep remembering it 🌸"
        db.save_message("assistant", reply)
        return JSONResponse({"success": True, "reply": reply, "action_performed": "cancelled"})

    db.clear_pending_action()
    return JSONResponse({"success": True, "reply": "Action completed 🌸"})

# Emergency STOP endpoint (hard killswitch)
@app.post("/api/stop")
async def stop_endpoint():
    global emergency_stop_triggered
    emergency_stop_triggered = True
    
    # Requirement 6: If STOP is triggered, cancel any pending proposal
    db.cancel_pending_proposal(reason="Emergency STOP button clicked in header")
    db.log_audit("STOP_TRIGGERED", "Emergency STOP button clicked in header.")
    
    return JSONResponse({
        "status": "stopped",
        "message": "🛑 Emergency STOP triggered. All processing halted immediately."
    })

# Resume endpoint
@app.post("/api/resume")
async def resume_endpoint():
    global emergency_stop_triggered
    emergency_stop_triggered = False
    db.log_audit("STOP_RESUMED", "Resume button clicked.")
    return JSONResponse({
        "status": "resumed",
        "message": "🌸 Welcome back! Everything is quiet and ready."
    })

# ----------------- Memory & Dev Endpoints -----------------

@app.get("/api/dev/facts")
async def dev_facts_endpoint():
    """Developer-only endpoint to inspect SQLite facts and audit logs when DEV_MODE=true."""
    is_dev = os.getenv("DEV_MODE", "false").strip().lower() in ("true", "1", "yes")
    if not is_dev:
        raise HTTPException(status_code=403, detail="Developer mode is disabled. Set DEV_MODE=true in .env to enable.")
    return {
        "dev_mode": True,
        "facts": db.get_all_facts(),
        "audit_logs": db.get_audit_logs(limit=25)
    }

@app.get("/api/facts")
async def get_facts_endpoint():
    """Returns all remembered facts."""
    return {"facts": db.get_all_facts()}

@app.post("/api/facts")
async def add_fact_endpoint(payload: FactCreateRequest):
    """Manually add a fact to memory."""
    new_id = db.add_fact(payload.fact, payload.category or "general")
    if not new_id:
        raise HTTPException(status_code=400, detail="Fact cannot be empty.")
    return {"success": True, "id": new_id}

@app.put("/api/facts/{fact_id}")
async def update_fact_endpoint(fact_id: int, payload: FactUpdateRequest):
    """Edit an existing remembered fact."""
    ok = db.update_fact(fact_id, payload.fact)
    if not ok:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"success": True}

@app.delete("/api/facts/{fact_id}")
async def delete_fact_endpoint(fact_id: int):
    """Delete a remembered fact."""
    ok = db.delete_fact(fact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"success": True}

@app.post("/api/purge")
async def purge_data_endpoint():
    """Wipes all user data (messages, facts, tasks) after confirmation."""
    db.purge_all_data()
    return {"success": True, "message": "All messages and memory have been wiped cleanly."}

# ----------------- Audit Log Endpoint -----------------

@app.get("/api/audit")
async def get_audit_endpoint():
    """Returns recent audit logs."""
    return {"logs": db.get_audit_logs(limit=50)}

# ----------------- Host Info & Static Files -----------------

@app.get("/api/info")
async def info_endpoint():
    port = int(os.environ.get("PORT", 8080))
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    is_dev = os.getenv("DEV_MODE", "false").strip().lower() in ("true", "1", "yes")
    return {
        "companion": "SINBHA",
        "local_ip": get_local_ip(),
        "port": port,
        "model": model,
        "dev_mode": is_dev,
        "emergency_stopped": emergency_stop_triggered
    }

# Serve the static UI files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    local_ip = get_local_ip()
    print("=" * 60)
    print("🌸 SINBHA is running!")
    print(f"👉 On your computer:  http://localhost:{port}")
    print(f"👉 On your phone:     http://{local_ip}:{port}")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
