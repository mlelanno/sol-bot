import requests
import json
from config import OLLAMA_BASE_URL, MODEL_NAME

def query_qwen(prompt: str, system_prompt: str = "", force_json: bool = True) -> dict:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096
        }
    }
    if force_json:
        payload["format"] = "json"

    # Timeout : 10s pour se connecter, 120s pour laisser le GPU charger et générer
    response = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=(10, 120))
    response.raise_for_status()
    raw_text = response.json().get("response", "{}")
    
    if force_json:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON", "raw": raw_text}
    return {"response": raw_text}
