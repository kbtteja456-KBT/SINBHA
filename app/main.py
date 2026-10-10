import os
import socket
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

# Load environment variables (.env)
load_dotenv()

from app.ai_brain import call_sinbha_brain, extract_explicit_facts
from app import database as db

app = FastAPI(title="SINBHA - Personal AI Companion")

# Emergency stop state tracker
emergency_stop_triggered = False

class ChatRequest(BaseModel):
    message: str

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

    # 1. Save user message to SQLite database
    db.save_message("user", user_msg)
    db.log_audit("CHAT_MESSAGE", f"User sent: '{user_msg[:80]}...'")

    # 2. Retrieve last 20 messages & remembered facts
    recent_history = db.get_recent_messages(limit=20)
    facts = db.get_all_facts()

    # 3. Call SINBHA's brain
    brain_result = await call_sinbha_brain(
        user_message=user_msg,
        chat_history=recent_history[:-1],
        remembered_facts=facts
    )
    ai_reply = brain_result.get("reply", "I'm right here with you 🌸")

    # 4. Save AI reply to SQLite database
    db.save_message("assistant", ai_reply)

    # 5. Extract new explicit facts in the background (Requirement 5)
    new_facts_saved = []
    try:
        extracted = await extract_explicit_facts(user_msg)
        for f in extracted:
            new_id = db.add_fact(f)
            if new_id:
                new_facts_saved.append(f)
    except Exception as e:
        print(f"Fact extraction note: {e}")

    return JSONResponse({
        "reply": ai_reply,
        "proposal": None,
        "new_facts": new_facts_saved
    })

# Emergency STOP endpoint (hard killswitch)
@app.post("/api/stop")
async def stop_endpoint():
    global emergency_stop_triggered
    emergency_stop_triggered = True
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

# ----------------- Memory (Facts) Endpoints -----------------

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
    return {
        "companion": "SINBHA",
        "local_ip": get_local_ip(),
        "port": port,
        "model": model,
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
