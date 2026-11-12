import asyncio
import time
import aiohttp
from wakeonlan import send_magic_packet
from config import GPU_SERVER_MAC, OLLAMA_BASE_URL

def wake_gpu_server() -> None:
    """
    Envoie un paquet magique Wake-on-LAN au serveur GPU.
    """
    send_magic_packet(GPU_SERVER_MAC)

async def is_gpu_ready() -> bool:
    """
    Teste la disponibilité de l'API Ollama sur le PC fixe avec un timeout de 1 seconde.
    """
    url = f"{OLLAMA_BASE_URL}/api/tags"
    timeout = aiohttp.ClientTimeout(total=1.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                return response.status == 200
    except Exception:
        return False

async def wait_for_gpu(timeout: float = 30.0) -> float:
    """
    Boucle jusqu'à ce que le PC fixe réponde et retourne le temps réel écoulé en secondes (boot_latency).
    Déclenche le Wake-on-LAN si le PC fixe n'est pas prêt.
    """
    start_time = time.monotonic()
    if await is_gpu_ready():
        return round(time.monotonic() - start_time, 4)

    wake_gpu_server()

    while (time.monotonic() - start_time) < timeout:
        if await is_gpu_ready():
            return round(time.monotonic() - start_time, 4)
        await asyncio.sleep(0.5)

    return round(time.monotonic() - start_time, 4)
