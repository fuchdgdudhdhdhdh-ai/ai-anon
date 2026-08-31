from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    AuthKeyUnregisteredError,
)

from config import API_ID, API_HASH, SESSION_NAME
from local_settings import STYLE_SAMPLES_LIMIT

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

_login_state = {"phone": None, "phone_code_hash": None}


async def ensure_connected():
    if not client.is_connected():
        await client.connect()


async def is_authorized() -> bool:
    await ensure_connected()
    try:
        return await client.is_user_authorized()
    except AuthKeyUnregisteredError:
        return False


async def send_code(phone: str):
    await ensure_connected()
    result = await client.send_code_request(phone)
    _login_state["phone"] = phone
    _login_state["phone_code_hash"] = result.phone_code_hash


async def confirm_code(code: str):
    """Возвращает 'ok' или 'need_password'. Бросает ValueError при неверном коде."""
    try:
        await client.sign_in(
            phone=_login_state["phone"],
            code=code,
            phone_code_hash=_login_state["phone_code_hash"],
        )
        return "ok"
    except SessionPasswordNeededError:
        return "need_password"
    except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
        raise ValueError("Код неверный или истёк, запроси новый через /relogin.") from e


async def confirm_password(password: str):
    await client.sign_in(password=password)
    return "ok"


async def resolve_chat(chat_ref: str):
    """chat_ref: t.me-ссылка, @username или числовой ID."""
    await ensure_connected()
    ref = chat_ref
    if ref.lstrip("-").isdigit():
        ref = int(ref)
    entity = await client.get_entity(ref)
    title = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(entity.id)
    return entity.id, title


async def collect_recent_own_messages(chat_id, limit: int = STYLE_SAMPLES_LIMIT) -> list:
    await ensure_connected()
    me = await client.get_me()
    texts = []
    async for msg in client.iter_messages(chat_id, limit=limit):
        if msg.sender_id == me.id and msg.message:
            texts.append(msg.message)
    return texts
