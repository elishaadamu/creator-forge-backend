import os
from app.config import settings

def call_llm(prompt: str, max_tokens: int = 1000, system_prompt: str = None) -> str:
    """
    Calls the active LLM provider configured by the admin (gemini, openai, claude).
    Gracefully falls back to other configured providers if the active one fails.
    """
    provider = settings.ACTIVE_AI_PROVIDER.lower().strip() if settings.ACTIVE_AI_PROVIDER else "gemini"
    
    # Establish priority list based on selected provider
    if provider == "openai":
        priority = ["openai", "gemini", "claude"]
    elif provider in ("claude", "anthropic"):
        priority = ["claude", "gemini", "openai"]
    else:
        priority = ["gemini", "claude", "openai"]

    errors = []
    for p in priority:
        if p == "gemini":
            if not settings.GEMINI_API_KEY:
                continue
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                if response and response.text:
                    print("\n" + "="*50)
                    print(f"🤖 [AI GENERATED RESPONSE - GEMINI]:\n{response.text.strip()}")
                    print("="*50 + "\n")
                    return response.text.strip()
                else:
                    raise ValueError("Gemini returned empty response text")
            except Exception as e:
                # Fallback to direct HTTP post if google-genai package fails / has issue
                try:
                    import httpx
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": max_tokens}
                    }
                    r = httpx.post(url, json=payload, timeout=30)
                    if r.status_code == 200:
                        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        print("\n" + "="*50)
                        print(f"🤖 [AI GENERATED RESPONSE - GEMINI HTTP]:\n{raw}")
                        print("="*50 + "\n")
                        return raw
                    else:
                        raise ValueError(f"HTTP Post Gemini API error: {r.text}")
                except Exception as inner_e:
                    errors.append(f"Gemini error: {e} | HTTP Fallback error: {inner_e}")
                    
        elif p == "openai":
            if not settings.OPENAI_API_KEY:
                continue
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                response = client.chat.completions.create(
                    model="gpt-5.5",
                    messages=messages,
                    max_tokens=max_tokens,
                )
                if response and response.choices:
                    content = response.choices[0].message.content.strip()
                    print("\n" + "="*50)
                    print(f"🤖 [AI GENERATED RESPONSE - OPENAI]:\n{content}")
                    print("="*50 + "\n")
                    return content
                else:
                    raise ValueError("OpenAI returned empty response")
            except Exception as e:
                errors.append(f"OpenAI error: {e}")

        elif p == "claude":
            if not settings.ANTHROPIC_API_KEY:
                continue
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                model = settings.AI_MODEL if settings.AI_MODEL else "claude-opus-4-6"
                # Handle system prompt if provided
                kwargs = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system_prompt:
                    kwargs["system"] = system_prompt
                message = client.messages.create(**kwargs)
                if message and message.content:
                    content = message.content[0].text.strip()
                    print("\n" + "="*50)
                    print(f"🤖 [AI GENERATED RESPONSE - CLAUDE]:\n{content}")
                    print("="*50 + "\n")
                    return content
                else:
                    raise ValueError("Claude returned empty response")
            except Exception as e:
                errors.append(f"Claude error: {e}")

    raise RuntimeError(f"All LLM generation attempts failed. Errors: {'; '.join(errors)}")
