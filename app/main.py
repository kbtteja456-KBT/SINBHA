import os
import socket
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="SINBHA - Personal AI Companion")

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

# API Chat Endpoint (Step 2: Friendly placeholder; Step 3 connects OpenRouter)
@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    user_msg = payload.message.strip()
    if not user_msg:
        return JSONResponse({"reply": "I'm listening whenever you want to talk 🌸", "proposal": None})
    
    # Check for STOP command in message
    if user_msg.upper() == "STOP":
        return JSONResponse({
            "reply": "🛑 STOP command received. I've cleared any pending actions. I'm right here whenever you're ready.",
            "proposal": None,
            "stopped": True
        })

    # Friendly placeholder response for Step 2
    friendly_replies = [
        "Hey! I'm here with you. My full brain connects in Step 3, but our chat connection is working smoothly! 🌸",
        "I hear you! How has your day been feeling so far?",
        "Got your message! I'm ready to learn more about you as soon as we hook up my brain."
    ]
    import random
    reply = random.choice(friendly_replies)
    
    return JSONResponse({
        "reply": reply,
        "proposal": None
    })

# Emergency STOP endpoint (hard killswitch)
@app.post("/api/stop")
async def stop_endpoint():
    return JSONResponse({
        "status": "stopped",
        "message": "🛑 Emergency STOP triggered. All processing halted immediately."
    })

# Host info helper
@app.get("/api/info")
async def info_endpoint():
    port = int(os.environ.get("PORT", 8080))
    return {
        "companion": "SINBHA",
        "local_ip": get_local_ip(),
        "port": port
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
