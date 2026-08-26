import os
from app.config import settings

def call_llm(prompt: str, max_tokens: int = 1000, system_prompt: str = None, api_keys: dict = None) -> str:
    """
    Calls the active LLM provider configured by the admin (gemini, openai, claude).
    Gracefully falls back to other configured providers if the active one fails.
    """
    provider = settings.ACTIVE_AI_PROVIDER.lower().strip() if settings.ACTIVE_AI_PROVIDER else "gemini"
    
    gemini_api_key = (api_keys.get("geminiKey") or api_keys.get("gemini_api_key")) if api_keys else None
    if not gemini_api_key:
        gemini_api_key = settings.GEMINI_API_KEY

    openai_api_key = (api_keys.get("openaiKey") or api_keys.get("openai_api_key")) if api_keys else None
    if not openai_api_key:
        openai_api_key = settings.OPENAI_API_KEY

    anthropic_api_key = (api_keys.get("anthropicKey") or api_keys.get("anthropic_api_key")) if api_keys else None
    if not anthropic_api_key:
        anthropic_api_key = settings.ANTHROPIC_API_KEY

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
            if not gemini_api_key:
                continue
            try:
                from google import genai
                client = genai.Client(api_key=gemini_api_key)
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
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": max_tokens}
                    }
                    r = httpx.post(url, json=payload, timeout=60)
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
            if not openai_api_key:
                continue
            try:
                import httpx
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_api_key}"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "max_tokens": max_tokens
                }
                r = httpx.post(url, json=payload, headers=headers, timeout=60.0)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}: {r.text}")
                
                res_data = r.json()
                content = res_data["choices"][0]["message"]["content"].strip()
                if content:
                    print("\n" + "="*50)
                    print(f"[AI GENERATED RESPONSE - OPENAI]:\n{content}")
                    print("="*50 + "\n")
                    return content
                else:
                    raise ValueError("OpenAI returned empty response")
            except Exception as e:
                errors.append(f"OpenAI error: {e}")

        elif p == "claude":
            if not anthropic_api_key:
                continue
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_api_key)
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
