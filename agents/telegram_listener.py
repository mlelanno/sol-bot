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
# Pipeline Narrative V2 : Temps Réel + Audit Gemini 2.5 Flash
# -------------------------------------------------------
BUFFER_FILE = os.path.join(BASE_DIR, "data", "tg_buffer.json")
AUDIT_FILE = os.path.join(BASE_DIR, "logs", "narrative_audit.jsonl")

def append_to_buffer(msg_text: str):
    if not msg_text or len(msg_text.strip()) < 5:
        return
    try:
        hist = json.load(open(BUFFER_FILE, encoding="utf-8")) if os.path.exists(BUFFER_FILE) else []
        if not isinstance(hist, list): hist = []
    except Exception:
        hist = []
    clean = msg_text.strip().replace("\n", " ")[:350]
    if clean not in hist:
        hist = (hist + [clean])[-50:]
        with open(BUFFER_FILE, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)

async def call_gemini_v2(messages_list):
    if not GEMINI_API_KEY or not messages_list:
        return None
    import aiohttp
    joined = "\n".join(f"- {m}" for m in messages_list[-25:])
    prompt = (
        "Tu es un analyste quantitatif Solana. Analyse ces messages Telegram récents et extrais les "
        "narratives/tickers crypto émergents. Réponds UNIQUEMENT en JSON valide avec exactement ces clés: "
        '{"external_catalyst": true/false, "shill_pattern_detected": true/false, '
        '"keywords": ["mot1", "ticker2"], "narrative_strength": 0 à 45, "summary": "résumé court"}.\n\n'
        f"Messages:\n{joined}"
    )
    url = f"{GEMINI_ENDPOINT}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12.0)) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"Gemini HTTP {resp.status}")
                    return None
                data = await resp.json()
                txt = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt)
    except Exception as e:
        logger.error(f"Erreur Gemini V2 : {e}")
        return None

async def run_narrative_cycle(batch_msgs):
    if not batch_msgs:
        return
    res = await call_gemini_v2(batch_msgs)
    if not res or not isinstance(res, dict):
        return
    from datetime import datetime
    now_iso = datetime.now().isoformat()
    audit_entry = {
        "timestamp": now_iso,
        "provider": "gemini-2.5-flash",
        "messages_count": len(batch_msgs),
        "result": res
    }
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

    keywords = [str(k).strip() for k in (res.get("keywords") or []) if len(str(k).strip()) >= 2]
    strength = float(res.get("narrative_strength") or 0)
    if keywords and strength > 0 and not res.get("shill_pattern_detected", False):
        add_narrative_signal(keywords, strength)
    logger.info(f"🧠 Audit IA enregistré : strength={strength}, keywords={keywords[:5]}")

@telegram_client.on(events.NewMessage())
async def handle_new_message(event):
    try:
        txt = event.raw_text or ""
        if len(txt.strip()) >= 8:
            append_to_buffer(txt)
            async with buffer_lock:
                message_buffer.append(txt.strip()[:300])
                if len(message_buffer) > 50:
                    message_buffer.pop(0)
    except Exception:
        pass

async def main():
    await telegram_client.start()
    logger.info("✅ Client Telegram connecté (V2 Temps Réel)")
    # Amorçage immédiat depuis les derniers messages des dialogues pour peupler le Dashboard tout de suite
    seed_msgs = []
    try:
        async for dialog in telegram_client.iter_dialogs(limit=15):
            if dialog.is_channel or dialog.is_group:
                async for msg in telegram_client.iter_messages(dialog.entity, limit=4):
                    if msg.raw_text and len(msg.raw_text.strip()) >= 10:
                        append_to_buffer(msg.raw_text)
                        seed_msgs.append(msg.raw_text.strip()[:300])
    except Exception as e:
        logger.warning(f"Seed warning: {e}")

    if seed_msgs:
        logger.info(f"🚀 Amorçage initial Gemini sur {len(seed_msgs)} messages récents...")
        await run_narrative_cycle(seed_msgs[-20:])

    while True:
        await asyncio.sleep(120)
        async with buffer_lock:
            batch = list(message_buffer)
            message_buffer.clear()
        if batch:
            await run_narrative_cycle(batch)

if __name__ == "__main__":
    with telegram_client:
        telegram_client.loop.run_until_complete(main())
