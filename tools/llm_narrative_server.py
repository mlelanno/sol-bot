#!/usr/bin/env python3
"""
llm_narrative_server.py — Serveur d'inférence LLM (Ollama) dédié au PC fixe.

Fonctionnalités :
- POST /classify : reçoit un tableau de messages texte, renvoie la classification
  structurée (external_catalyst, shill_pattern_detected, keywords, narrative_strength)
- GET /health : vérifie que le serveur 24/7 est allumé (et que Ollama est reachable)

Configuration : variable d'environnement OLLAMA_MODEL (défaut : qwen2.5:7b)
"""

import os
import json
import uvicorn
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

# ── Configuration ─────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))
PORT = int(os.getenv("PORT", "8001"))

app = FastAPI(
    title="LLM Narrative Inference Server",
    description="Serveur d'inférence NLP sur le PC fixe — détection de catalysts "
                "culturels / spam / shilling ordonné.",
    version="1.0.0",
)

# Modèle FastAPI
class ClassifyRequest(BaseModel):
    messages: List[str]


class ClassifyResponse(BaseModel):
    external_catalyst: bool
    shill_pattern_detected: bool
    keywords: List[str]
    narrative_strength: int

# ── Prompt système strict ─────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Tu es un filtre de contenu critique pour un bot de trading quantitatif "
    "Solana. Analyse le message fourni et réponds SOLEMENT au format JSON "
    "strictement valide (pas de texte autre, pas de commentaires). "
    "Réponds avec les champs EXACTEMENT comme ceci :\n"
    "{\n"
    '  "external_catalyst": true|false,\n'
    '  "shill_pattern_detected": true|false,\n'
    '  "keywords": ["mot1", "mot2", ...],\n'
    '  "narrative_strength": 0-100\n'
    "}\n\n"
    "Règles :\n"
    "1. external_catalyst : vrai seulement si le message décrit un événement "
    "réel (nouvelle, macro, réglementaire, perpétuel, etc.) qui affecterait "
    "l'actif de manière indépendante du market.\n"
    "2. shill_pattern_detected : vrai si le message tente de créer un sentiment "
    "artificiel, utilise un shill coordonné, des urgences fausses, des liens "
    "de pommeau, ou est écrit dans un but sell/marketing plutôt qu'informatif.\n"
    "3. keywords : liste d'au plus 10 mots-clés les plus significatifs pour le "
    "trading (pas de stopwords).\n"
    "4. narrative_strength : de 0 à 100, la force de l'histoire / de la "
    "narrative marketing dans le message (0 = rien, 100 = hype maximal)."
)

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=dict)
async def health_check():
    """
    Vérifie que le serveur est up et que Ollama est reachable.
    Sert à faire un ping avant d'envoyer un batch de messages.
    """
    status = {
        "server": "up",
        "ollama_reachable": False,
        "model": OLLAMA_MODEL,
    }
    try:
        import requests
        resp = requests.post(
            f"{OLLAMA_URL}?model={OLLAMA_MODEL}",
            json={"prompt": "", "stream": False, "keep_alive": -1},
            timeout=5,
        )
        status["ollama_reachable"] = resp.status_code == 200
    except ImportError:
        # requests n'est pas installé pour des raisons de rapidité
        status["ollama_reachable"] = False
    except Exception:
        status["ollama_reachable"] = False
    return status


@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    """
    Reçoit la liste des messages texte et renvoie la classification structurée.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Le champ 'messages' est vide.")

    # Construire le prompt complet (messages concaténés)
    user_text = "\n\n".join(request.messages)

    prompt = f"{SYSTEM_PROMPT}\n\n{messages}"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": 512,
        },
    }

    try:
        import requests
        resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # L'object de réponse Ollama contient le texte complet
        full_text = data.get("response", "")
        if not full_text:
            raise ValueError("Réponse vide de Ollama.")

        # Extraire le JSON du texte (il peut y avoir du texte avant/après)
        start = full_text.find("{")
        end = full_text.rfind("}") + 1
        if start == -1 or end <= start:
            raise ValueError("JSON non trouvé dans la réponse de Ollama.")

        json_str = full_text[start:end]
        result = json.loads(json_str)

        # Validation des champs obligatoires
        required = {"external_catalyst", "shill_pattern_detected", "keywords", "narrative_strength"}
        missing = required - set(result.keys())
        if missing:
            raise ValueError(f"Champs manquants dans la réponse : {missing}")

        # S'assurer que keywords est une liste
        if not isinstance(result["keywords"], list):
            result["keywords"] = []

        # S'assurer que narrative_strength est un int
        result["narrative_strength"] = int(result["narrative_strength"])

        return ClassifyResponse(**result)

    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=503,
            detail=f"Timeout (>{OLLAMA_TIMEOUT}s) avec Ollama à {OLLAMA_URL}",
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="La bibliothèque 'requests' est requise pour ce module.",
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Connexion à Ollama impossible : {e}",
        )
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Réponse JSON invalide de Ollama : {e}. Réponse brute : {full_text[:500]}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne : {e}",
        )


if __name__ == "__main__":
    print(f"🚀 LLM Narrative Server démarré sur le port {PORT}")
    print(f"   Modèle Ollama      : {OLLAMA_MODEL}")
    print(f"   URL Ollama         : {OLLAMA_URL}")
    print(f"   Timeout            : {OLLAMA_TIMEOUT}s")
    print(f"   Endpoints          : GET /health, POST /classify")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
if __name__ == "__main__":
    print(f"🚀 LLM Narrative Server démarré sur le port {PORT}")
    print(f"   Modèle Ollama      : {OLLAMA_MODEL}")
    print(f"   URL Ollama         : {OLLAMA_URL}")
    print(f"   Timeout            : {OLLAMA_TIMEOUT}s")
    print(f"   Endpoints          : GET /health, POST /classify")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

# Modèle FastAPI
class ClassifyRequest(BaseModel):
    messages: List[str]


class ClassifyResponse(BaseModel):
    external_catalyst: bool
    shill_pattern_detected: bool
    keywords: List[str]
    narrative_strength: int