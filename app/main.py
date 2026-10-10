import os
import socket
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables (.env)
load_dotenv()

from app.ai_brain import call_sinbha_brain

app = FastAPI(title="SINBHA - Personal AI Companion")

# Emergency stop state tracker
emergency_stop_triggered = False

# Simple in-memory recent messages for current session (Step 4 adds full SQLite memory)
recent_messages = []

class ChatRequest(BaseModel):
    message: str

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

# API Chat Endpoint
@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    global emergency_stop_triggered
    user_msg = payload.message.strip()
    
    if not user_msg:
        return JSONResponse({
            "reply": "I'm listening whenever you want to talk 🌸",
            "proposal": None
        })
    
    # RULE 3: STOP check comes FIRST - NEVER calls the AI if STOP is commanded or active
    if user_msg.upper() == "STOP":
        emergency_stop_triggered = True
        return JSONResponse({
            "reply": "🛑 STOP command received. All operations halted immediately. I'm right here whenever you want to chat normally again.",
            "proposal": None,
            "stopped": True
        })

    # If emergency stop was previously triggered, resume normal friendly conversation
    if emergency_stop_triggered:
        emergency_stop_triggered = False

    # Append user message to recent session
    recent_messages.append({"role": "user", "content": user_msg})

    # Call SINBHA's brain with OpenRouter
    brain_result = await call_sinbha_brain(user_msg, chat_history=recent_messages[:-1])
    ai_reply = brain_result.get("reply", "I'm right here with you 🌸")

    # Append AI reply to session
    recent_messages.append({"role": "assistant", "content": ai_reply})

    # Keep in-memory list tidy
    if len(recent_messages) > 30:
        recent_messages.pop(0)

    return JSONResponse({
        "reply": ai_reply,
        "proposal": None
    })

# Emergency STOP endpoint (hard killswitch)
@app.post("/api/stop")
async def stop_endpoint():
    global emergency_stop_triggered
    emergency_stop_triggered = True
    return JSONResponse({
        "status": "stopped",
        "message": "🛑 Emergency STOP triggered. All processing halted immediately."
    })

# Host info helper
@app.get("/api/info")
async def info_endpoint():
    port = int(os.environ.get("PORT", 8080))
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
    return {
        "companion": "SINBHA",
        "local_ip": get_local_ip(),
        "port": port,
        "model": model
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
