from telethon import events
from telethon.errors import AuthKeyUnregisteredError

import storage
import telethon_manager as tm
import ai_client

_history = {}  # chat_id -> [{"role": .., "content": ..}, ...]
_listener_started = False
_handler_registered = False


def _match_trigger(text: str, triggers: dict):
    """Ищет первую подходящую по подстроке фразу. triggers: id -> {phrase,type,content}."""
    low = text.lower()
    for trg in triggers.values():
        phrase = trg.get("phrase", "")
        if phrase and phrase in low:
            return trg
    return None


async def start_listener():
    global _listener_started, _handler_registered
    if _listener_started:
        return
    _listener_started = True

    await tm.ensure_connected()
    client = tm.client
    data = storage.load()
    chat_id = data.get("chat_id")
    if not chat_id:
        _listener_started = False
        return

    me = await client.get_me()

    if not _handler_registered:
        @client.on(events.NewMessage(chats=chat_id))
        async def handler(event):
            if event.sender_id == me.id:
                return
            text = event.raw_text or ""
            if not text.strip():
                return

            data = storage.load()
            triggers = data.get("triggers", {})
            trg = _match_trigger(text, triggers)
            if trg:
                # и текстовые ответы, и ссылки отправляются одинаково —
                # Telegram сам покажет превью ссылки
                await event.respond(trg["content"])
                return

            system_prompt = ai_client.build_system_prompt(
                data.get("persona_name", "Алексей Нейросеть"),
                data.get("style_samples", []),
            )
            hist = _history.setdefault(chat_id, [])
            try:
                reply = ai_client.generate_reply(system_prompt, hist, text)
            except Exception:
                reply = "Не смог сгенерировать ответ, попробуй чуть позже 🙏"

            hist.append({"role": "user", "content": text})
            hist.append({"role": "assistant", "content": reply})
            if len(hist) > 20:
                del hist[: len(hist) - 20]

            await event.respond(reply)

        _handler_registered = True

    try:
        await client.run_until_disconnected()
    except AuthKeyUnregisteredError:
        await storage.update(logged_in=False)
        import bot as control_bot
        await control_bot.notify_owner(
            "⚠️ Сессия слетела, нужно войти заново. Напиши /relogin в этом боте."
        )
    finally:
        _listener_started = False
