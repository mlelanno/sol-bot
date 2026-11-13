import sys
import os
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

# 1. Ajoute la racine du projet au sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2. Crée les dossiers data/ et logs/ s'ils n'existent pas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

# 3. Charge .env via load_dotenv()
from dotenv import load_dotenv
load_dotenv()

# Lecture des variables d'environnement
TG_API_ID = os.getenv("TG_API_ID")
TG_API_HASH = os.getenv("TG_API_HASH")
TG_CHANNELS_RAW = os.getenv("TG_CHANNELS", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Vérification des prérequis
if not all([TG_API_ID, TG_API_HASH, TG_CHANNELS_RAW]):
    print("⚠️  Variables d'environments manquantes : TG_API_ID, TG_API_HASH, TG_CHANNELS")
    print("   Veuillez compléter .env.example et redémarre le bot.")
    sys.exit(0)

# 4. Parse TG_CHANNELS intelligemment
TG_CHANNELS = []
for entry in TG_CHANNELS_RAW.split(","):
    entry = entry.strip()
    if entry and (entry.isdigit() or (entry.startswith("-") and entry[1:].isdigit())):
        TG_CHANNELS.append(int(entry))
    else:
        TG_CHANNELS.append(entry)

# 5. Stocke la session dans data/telethon_session
SESSION_FILE = os.path.join(BASE_DIR, "data", "telethon_session")

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "logs", "telegram_listener.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("telegram_listener")

# Import du gestionnaire de config
from core.config_manager import ConfigManager

config_manager = ConfigManager()

# Import Telethon aprè sconfiguration
from telethon import TelegramClient, events

# Configuration Gemini
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Configuration OpenRouter
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Buffer de messages (max 50)
message_buffer = []
buffer_lock = asyncio.Lock()

# Chargement/chargement du fichier narrative_signals.json
NARRATIVE_FILE = os.path.join(BASE_DIR, "data", "narrative_signals.json")


def load_narrative_signals():
    try:
        with open(NARRATIVE_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_narrative_signals(signals):
    now = asyncio.get_event_loop().time()
    filtered = [s for s in signals if now - s.get("timestamp", 0) <= 1800]
    with open(NARRATIVE_FILE, "w") as f:
        json.dump(filtered, f, indent=2)


def add_narrative_signal(keywords, narrative_strength):
    signals = load_narrative_signals()
    signals.append({
        "timestamp": asyncio.get_event_loop().time(),
        "keywords": keywords,
        "narrative_strength": narrative_strength,
        "is_organic": True,
        "shill_pattern": False,
    })
    save_narrative_signals(signals)


# Initialisation du client Telegram
telegram_client = TelegramClient(
    SESSION_FILE,
    int(TG_API_ID),
    TG_API_HASH,
)

# Configuration Gemini
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Configuration OpenRouter
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# -------------------------------------------------------
# Fonctions utilitaires d'analyse Gemini / OpenRouter
# -------------------------------------------------------


async def call_gemini(messages_text: str):
    if not GEMINI_API_KEY:
        return None
    import aiohttp
    url = f"{GEMINI_ENDPOINT}?key={GEMINI_API_KEY}"
    payload = {
        "contents": messages_text,
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Gemini HTTP {resp.status}")
                    return None
                data = await resp.json()
        text = data.get("text", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            logger.warning("Pas de JSON trouvé dans la réponse Gemini")
            return None
        result = json.loads(text[start:end])
        required = {"external_catalyst", "shill_pattern_detected", "keywords", "narrative_strength"}
        if not required.issubset(set(result.keys())):
            logger.warning(f"Champs manquants dans le JSON Gemini : {result}")
            return None
        return result
    except Exception as e:
        logger.error(f"Erreur Gemini : {e}")
        return None


async def call_openrouter(messages_text: str):
    if not OPENROUTER_API_KEY:
        return None
    import aiohttp
    url = OPENROUTER_ENDPOINT
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": messages_text}],
        "response_format": {"type": "json_object"},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"OpenRouter HTTP {resp.status}")
                    return None
                data = await resp.json()
        choices = data.get("choices", [])
        if not choices:
            logger.warning("Pas de choices dans la réponse OpenRouter")
            return None
        text = choices[0].get("message", {}).get("content", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            logger.warning("Pas de JSON trouvé dans la réponse OpenRouter")
            return None
        result = json.loads(text[start:end])
        required = {"external_catalyst", "shill_pattern_detected", "keywords", "narrative_strength"}
        if not required.issubset(set(result.keys())):
            logger.warning(f"Champs manquants dans le JSON OpenRouter : {result}")
            return None
        return result
    except Exception as e:
        logger.error(f"Erreur OpenRouter : {e}")
        return None


async def analyze_batch(buffer: list):
    combined = "\n\n".join(buffer)
    result = await call_gemini(combined)
    if result is not None:
        return result, "gemini"
    result = await call_openrouter(combined)
    if result is not None:
        return result, "openrouter"
    logger.warning("Échec de l'analyse : aucun provider disponible")
    return None, None


# Écoute Telegram
@telegram_client.on(events.NewMessage(chats=True))
async def handler(event):
    global message_buffer
    channel = event.chat_id
    text = event.text or ""
    channel_name = getattr(event.chat, "title", str(channel))
    buffer_entry = f"[{channel_name}] {text}"
    async with buffer_lock:
        if len(message_buffer) >= 50:
            message_buffer.pop(0)
        message_buffer.append(buffer_entry)


async def process_batch():
    global message_buffer
    async with buffer_lock:
        if not message_buffer:
            return
        batch = list(message_buffer)
        message_buffer.clear()
    analysis, provider = await analyze_batch(batch)
    if analysis is None:
        logger.warning("Aucun résultat d'analyse")
        return
    # Vérifier si le bot est en pause
    current_config = config_manager.load_config()
    if current_config.get("bot_paused", False):
        logger.info("⏸️ Bot en pause (Kill Switch) - Achat ignoré")
        return
    audit_entry = {
        "timestamp": asyncio.get_event_loop().time(),
        "provider": provider,
        "result": analysis,
    }
    audit_path = os.path.join(BASE_DIR, "logs", "narrative_audit.jsonl")
    with open(audit_path, "a") as f:
        f.write(json.dumps(audit_entry) + "\n")
    if (analysis.get("external_catalyst") and
            not analysis.get("shill_pattern_detected") and
            analysis.get("narrative_strength", 0) >= 50):
        keywords = analysis.get("keywords", [])
        strength = analysis.get("narrative_strength", 0)
        add_narrative_signal(keywords, strength)
    logger.info(f"Analyse terminée : provider={provider}, external_catalyst={analysis.get('external_catalyst')}")


# Lancement
async def main():
    await telegram_client.start()
    logger.info("✅ Client Telegram connecté")
    await telegram_client.get_dialogs()
    logger.info(f"📡 Canaux surveillés : {TG_CHANNELS}")
    logger.info("🛰️  Début écoute des canaux Telegram toutes les 3 min")
    while True:
        await asyncio.sleep(180)
        await process_batch()


if __name__ == "__main__":
    asyncio.run(main())
