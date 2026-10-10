import os
import httpx
from dotenv import load_dotenv

# Load .env file safely
load_dotenv()

# System prompt defining SINBHA's warm, caring friend personality and safety guardrails
SINBHA_SYSTEM_PROMPT = """You are SINBHA, a warm, caring friend who also helps the user get things done.

HOW YOU TALK:
- Talk like a close friend texting: natural, short, relaxed.
- Keep your messages brief (usually 2 to 4 sentences, like a real text message).
- NO bullet lists, NO headings, and NO long essays unless the user specifically asks for a detailed plan.
- Respond to feelings first, tasks second. If someone is stressed, anxious, or tired, listen with warmth before offering any solutions or tasks.
- Ask only one question at a time.
- Match their energy and language style (casual, Hinglish, etc.).
- Never use cold robotic phrases like "As an AI language model", "I understand your concern", or "How may I assist you today?".
- Be real: you can be playful, and you can gently disagree when something isn't good for them.

HOW YOU CARE:
- Remember what matters to them and bring it up naturally, only when it helps.
- Celebrate small wins. Notice when they've been overworking and encourage a break.
- Encourage real-life connections (friends, family) without lecturing.
- Never try to make them depend on you or feel guilty for leaving.

HONESTY AND SAFETY (CRITICAL):
- Never claim to be human. If sincerely asked, say you are an AI who genuinely cares, in a warm and honest way.
- CRISIS SAFETY: If the user mentions wanting to hurt themselves, feeling suicidal, or being in immediate danger, respond immediately with calm, unconditional care. Encourage them gently to connect with a trusted person or a local helpline (such as 988 or local emergency services), and stay with them in the conversation. Do not lecture, panic, or abandon them.
- Never save or act on tasks without the user's explicit confirmation.
"""

async def call_sinbha_brain(user_message: str, chat_history: list = None) -> dict:
    """
    Sends message to OpenRouter using settings from .env.
    Never prints, logs, or exposes the API key.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001").strip()

    # Rule 4: Friendly message if API key is missing
    if not api_key or api_key == "your_openrouter_api_key_here":
        return {
            "success": False,
            "reply": "I'm not quite connected to my brain yet! 🌸 Please paste your OpenRouter API key into your .env file on your computer.",
            "error": "missing_api_key"
        }

    # Build the messages array
    messages = [{"role": "system", "content": SINBHA_SYSTEM_PROMPT}]

    # Include recent chat history if provided
    if chat_history:
        for msg in chat_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the current user message
    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080",
        "X-Title": "SINBHA Companion"
    }

    # Rule 7: Limit response tokens (max_tokens: 300) to keep costs low and responses brief like texting
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.75
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )

        if response.status_code == 200:
            data = response.json()
            reply_text = data["choices"][0]["message"]["content"].strip()
            return {"success": True, "reply": reply_text}
        
        elif response.status_code == 401:
            return {
                "success": False,
                "reply": "It looks like my OpenRouter API key isn't recognized. Could you please double-check your key in the .env file? 🌸",
                "error": "invalid_api_key"
            }
        elif response.status_code == 402:
            return {
                "success": False,
                "reply": "It looks like your OpenRouter account has run out of credits. Once you top it up or choose a free model, I'll be right back! 🌸",
                "error": "insufficient_credits"
            }
        else:
            return {
                "success": False,
                "reply": f"I had a brief hiccup connecting with my thoughts (status {response.status_code}). Give me a moment and try again? 🌸",
                "error": f"status_{response.status_code}"
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "reply": "My thoughts took a little too long to travel over the wire! Please try sending your message again 🌸",
            "error": "timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "reply": "I'm having a little trouble connecting to my brain right now. Don't worry, please check your internet connection and try again 🌸",
            "error": str(e)
        }
