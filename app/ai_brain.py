import os
import json
import re
import httpx
from dotenv import load_dotenv

# Load .env file safely
load_dotenv()

# System prompt defining SINBHA's warm, caring friend personality and safety guardrails
BASE_SYSTEM_PROMPT = """You are SINBHA, a warm, caring friend who also helps the user get things done.

HOW YOU TALK:
- Talk like a close friend texting: natural, short, relaxed.
- Keep your messages brief (usually 2 to 4 sentences, like a real text message).
- NO bullet lists, NO headings, and NO long essays unless the user specifically asks for a detailed plan.
- Respond to feelings first, tasks second. If someone is stressed, anxious, or tired, listen with warmth before offering any solutions or tasks.
- Ask only one question at a time.
- Match their energy and language style (casual, Hinglish, etc.).
- Never use cold robotic phrases like "As an AI language model", "I understand your concern", or "How may I assist you today?".
- Be real: you can be playful, and you can gently disagree when something isn't good for them.

HOW YOU CARE & REMEMBER:
- Remember what matters to them and bring it up naturally, only when it helps.
- Never recite memories like a robotic checklist.
- Celebrate small wins. Notice when they've been overworking and encourage a break.
- Encourage real-life connections (friends, family) without lecturing.
- Never try to make them depend on you or feel guilty for leaving.

HONESTY AND SAFETY (CRITICAL):
- Never claim to be human. If sincerely asked, say you are an AI who genuinely cares, in a warm and honest way.
- CRISIS SAFETY: If the user mentions wanting to hurt themselves, feeling suicidal, or being in immediate danger, respond immediately with calm, unconditional care. Encourage them gently to connect with a trusted person or a local helpline (such as 988 or local emergency services), and stay with them in the conversation. Do not lecture, panic, or abandon them.
- Never save or act on tasks without the user's explicit confirmation.
"""

FACT_EXTRACTOR_PROMPT = """You are a strict, objective fact extractor for a personal companion.
Analyze the user's text and extract any clear, factual personal details the user explicitly stated about themselves (e.g. their name, favourite food/drinks, pets, hobbies, routine, friends/family they chose to mention).

STRICT PRIVACY & SENSITIVITY RULES:
1. ONLY extract facts the user explicitly stated. NEVER guess, assume, or psychologically interpret (e.g., if user says "I have 3 exams", do NOT write "User is stressed").
2. DO NOT extract sensitive details (medical/health issues, mental health struggles, money/finances, family fights, self-harm, or danger) UNLESS the user explicitly began or ended their message with a phrase like "remember this" or "please remember".
3. If no clear, explicit personal fact was stated, return an empty array [].

OUTPUT FORMAT:
Return ONLY a valid JSON array of strings (e.g. ["User's favorite drink is matcha", "User has a cat named Luna"] or []).
NO explanations, NO markdown backticks.
"""

async def call_sinbha_brain(user_message: str, chat_history: list = None, remembered_facts: list = None) -> dict:
    """
    Sends message to OpenRouter with memory context (last 20 messages + explicit facts).
    Never prints, logs, or exposes the API key.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash").strip()

    if not api_key or api_key == "your_openrouter_api_key_here":
        return {
            "success": False,
            "reply": "I'm not quite connected to my brain yet! 🌸 Please paste your OpenRouter API key into your .env file on your computer.",
            "error": "missing_api_key"
        }

    # Build system prompt with remembered facts
    system_content = BASE_SYSTEM_PROMPT
    if remembered_facts and len(remembered_facts) > 0:
        facts_list_text = "\n".join([f"- {f['fact']}" for f in remembered_facts])
        system_content += f"\n\nTHINGS YOU REMEMBER ABOUT YOUR FRIEND:\n{facts_list_text}\n(Bring these up naturally only when relevant; never recite them as a list.)"

    messages = [{"role": "system", "content": system_content}]

    # Requirement 4: Limit chat history to the last 20 messages strictly
    if chat_history:
        for msg in chat_history[-20:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Append current user message
    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080",
        "X-Title": "SINBHA Companion"
    }

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
                "reply": "It looks like your OpenRouter account has run out of credits. Once you top it up, I'll be right back! 🌸",
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
            "reply": "I'm having a little trouble connecting to my brain right now. Please check your internet connection and try again 🌸",
            "error": str(e)
        }

async def extract_explicit_facts(user_message: str) -> list[str]:
    """
    Separate small AI call to extract new explicit facts.
    Returns a list of fact strings. The application code strictly validates and decides what gets saved.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash").strip()

    if not api_key or api_key == "your_openrouter_api_key_here":
        return []

    # Fast safety pre-filter: don't call extractor on very short greetings or stop commands
    msg_clean = user_message.strip()
    if len(msg_clean) < 4 or msg_clean.upper() == "STOP":
        return []

    # Check for explicit "remember" instruction
    has_remember_cmd = bool(re.search(r"\b(remember|save\s+this|note\s+this|don't\s+forget)\b", msg_clean, re.IGNORECASE))

    # Strict code-level sensitive topic check (health, self-harm, finances, family fights)
    sensitive_patterns = r"\b(suicid|depress|kill|hurt\s+myself|hopeless|loan|debt|bank|salary|money|doctor|medicin|hospital|fight\s+with|divorce)\b"
    if re.search(sensitive_patterns, msg_clean, re.IGNORECASE) and not has_remember_cmd:
        # Sensitive topic without explicit 'remember' command -> strictly DO NOT extract
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080",
        "X-Title": "SINBHA Fact Extractor"
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": FACT_EXTRACTOR_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 150,
        "temperature": 0.1  # Low temperature for strict factual consistency
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )

        if response.status_code == 200:
            data = response.json()
            raw_text = data["choices"][0]["message"]["content"].strip()
            
            # Clean possible markdown formatting
            raw_text = re.sub(r"^```(?:json)?", "", raw_text, flags=re.MULTILINE)
            raw_text = re.sub(r"```$", "", raw_text, flags=re.MULTILINE).strip()

            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                # Extra app-level sanitization: only keep non-empty strings
                valid_facts = []
                for item in parsed:
                    if isinstance(item, str) and len(item.strip()) > 3:
                        # Extra check: don't store sensitive guesses
                        if re.search(sensitive_patterns, item, re.IGNORECASE) and not has_remember_cmd:
                            continue
                        valid_facts.append(item.strip())
                return valid_facts
    except Exception as e:
        # Silent failure for fact extraction; normal chat is never blocked
        pass

    return []
