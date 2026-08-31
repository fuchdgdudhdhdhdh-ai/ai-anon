import json
import os
import asyncio

from config import DATA_FILE
from local_settings import DEFAULT_PERSONA_NAME

_lock = asyncio.Lock()

DEFAULTS = {
    "phone": None,
    "chat_id": None,
    "style_samples": [],
    # triggers: { "<id>": {"phrase": str, "type": "text"|"link", "content": str} }
    "triggers": {},
    "persona_name": DEFAULT_PERSONA_NAME,
    "logged_in": False,
}


def _ensure_file():
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)


def load() -> dict:
    _ensure_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    return data


async def save(data: dict):
    async with _lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


async def update(**kwargs) -> dict:
    data = load()
    data.update(kwargs)
    await save(data)
    return data
