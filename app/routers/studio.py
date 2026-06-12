from fastapi import APIRouter, Request
from pydantic import BaseModel
from openai import OpenAI
import json
import re
import logging

from app.config import settings

router = APIRouter(prefix="/api/studio", tags=["studio"])

class GenerateRequest(BaseModel):
    system_prompt: str
    prompt: str


@router.post("/generate")
def generate_studio_content(req: GenerateRequest, request: Request):
    try:
        # Read custom key from headers if provided
        nvidia_key = request.headers.get("x-nvidia-api-key", "").strip() or settings.NVIDIA_API_KEY
        if not nvidia_key:
            return {"content": "Error: NVIDIA API Key not configured. Enter it in settings."}

        client_local = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_key
        )

        completion = client_local.chat.completions.create(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=[
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.prompt}
            ],
            temperature=1,
            top_p=0.95,
            max_tokens=16384,
            extra_body={"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":16384},
            stream=False
        )
        
        if not completion.choices:
            return {"content": "Error: Nvidia Nemotron returned no choices."}
            
        content = completion.choices[0].message.content
        
        # Try to extract JSON block if Nemotron outputted thinking before it
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, flags=re.DOTALL | re.IGNORECASE)
        if json_match:
            cleaned = json_match.group(1).strip()
        else:
            cleaned = content.strip()
            # If no markdown block but looks like JSON
            if (cleaned.startswith('{') and cleaned.endswith('}')) or (cleaned.startswith('[') and cleaned.endswith(']')):
                pass
            else:
                return {"content": cleaned}
        
        try:
            parsed = json.loads(cleaned)
            return parsed  # Returns the array or object directly
        except Exception:
            return {"content": cleaned}
            
    except Exception as e:
        logging.error(f"Studio generation error: {str(e)}")
        return {"content": f"(API Call Failed: {str(e)})"}
