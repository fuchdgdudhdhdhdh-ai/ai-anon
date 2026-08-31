import asyncio
import logging
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

import config
import storage
import telethon_manager as tm
import userbot_runtime
from local_settings import TRIGGER_PHRASE_MAX_LEN, TRIGGER_CONTENT_MAX_LEN

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class Login(StatesGroup):
    phone = State()
    code = State()
    password = State()
    chat = State()
    style_confirm = State()


class TriggerFlow(StatesGroup):
    phrase = State()
    choose_type = State()
    content = State()


def owner_only(handler):
    async def wrapper(event, *args, **kwargs):
        user = event.from_user
        if config.OWNER_ID and user.id != config.OWNER_ID:
            if isinstance(event, Message):
                await event.answer("Этот бот приватный.")
            return
        return await handler(event, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Вход в аккаунт-персонаж
# ---------------------------------------------------------------------------

def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def code_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for d in "1234567890":
        row.append(InlineKeyboardButton(text=d, callback_data=f"code:{d}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="⌫ Стереть", callback_data="code:back"),
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="code:confirm"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
@owner_only
async def start(message: Message, state: FSMContext):
    data = storage.load()
    if data["logged_in"] and await tm.is_authorized():
        await message.answer(
            "Аккаунт уже авторизован и активен ✅\n"
            "Команды: /relogin — перелогиниться, /setchat — сменить чат, "
            "/style — обновить стиль, /triggers — триггеры и ссылки, /status — статус."
        )
        return
    await message.answer(
        f"Привет! Настроим вход в аккаунт «{data['persona_name']}».\n\n"
        "Отправь номер телефона в формате +7... или нажми кнопку ниже.",
        reply_markup=phone_keyboard(),
    )
    await state.set_state(Login.phone)


@dp.message(Command("relogin"))
@owner_only
async def relogin(message: Message, state: FSMContext):
    await start(message, state)


@dp.message(Command("status"))
@owner_only
async def status(message: Message):
    data = storage.load()
    ok = await tm.is_authorized()
    await message.answer(
        f"Авторизован: {'да' if ok else 'нет'}\n"
        f"Чат: {data.get('chat_id')}\n"
        f"Примеров стиля: {len(data.get('style_samples', []))}\n"
        f"Триггеров/ссылок: {len(data.get('triggers', {}))}"
    )


@dp.message(Login.phone, F.contact)
@owner_only
async def phone_from_contact(message: Message, state: FSMContext):
    await process_phone(message, state, message.contact.phone_number)


@dp.message(Login.phone, F.text)
@owner_only
async def phone_from_text(message: Message, state: FSMContext):
    await process_phone(message, state, message.text.strip())


async def process_phone(message: Message, state: FSMContext, phone: str):
    if not phone.startswith("+"):
        phone = "+" + phone.lstrip("+")
    await message.answer("Отправляю код...", reply_markup=ReplyKeyboardRemove())
    try:
        await tm.send_code(phone)
    except Exception as e:
        await message.answer(f"Не удалось отправить код: {e}")
        return
    await storage.update(phone=phone)
    await state.update_data(code="")
    await message.answer("Введи код через кнопки ниже:", reply_markup=code_keyboard(""))
    await state.set_state(Login.code)


@dp.callback_query(Login.code, F.data.startswith("code:"))
@owner_only
async def code_input(call: CallbackQuery, state: FSMContext):
    action = call.data.split(":", 1)[1]
    data = await state.get_data()
    code = data.get("code", "")

    if action == "back":
        code = code[:-1]
    elif action == "confirm":
        if not code:
            await call.answer("Сначала введи код", show_alert=True)
            return
        try:
            result = await tm.confirm_code(code)
        except ValueError as e:
            await call.answer(str(e), show_alert=True)
            await state.update_data(code="")
            await call.message.edit_text("Введи код заново:", reply_markup=code_keyboard(""))
            return
        if result == "need_password":
            await call.message.edit_text(
                "Нужен пароль двухфакторной аутентификации.\n"
                "Отправь его следующим сообщением (после ввода я его сразу удалю из чата)."
            )
            await state.set_state(Login.password)
            await call.answer()
            return
        await finish_login(call.message, state)
        await call.answer()
        return
    else:
        if len(code) < 8:
            code += action

    await state.update_data(code=code)
    masked = "•" * len(code)
    try:
        await call.message.edit_text(
            f"Введи код через кнопки ниже:\nКод: {masked}", reply_markup=code_keyboard(code)
        )
    except Exception:
        pass
    await call.answer()


@dp.message(Login.password, F.text)
@owner_only
async def password_input(message: Message, state: FSMContext):
    try:
        await tm.confirm_password(message.text.strip())
    except Exception as e:
        await message.answer(f"Не удалось войти: {e}. Попробуй ещё раз.")
        return
    try:
        await message.delete()
    except Exception:
        pass
    await finish_login(message, state)


async def finish_login(message: Message, state: FSMContext):
    await storage.update(logged_in=True)
    await message.answer(
        "Вход выполнен ✅\n\nТеперь пришли ссылку/юзернейм/ID чата "
        "(t.me/..., @username или числовой ID), в котором персонаж будет общаться."
    )
    await state.set_state(Login.chat)


@dp.message(Login.chat, F.text)
@owner_only
async def chat_input(message: Message, state: FSMContext):
    ref = message.text.strip()
    try:
        chat_id, title = await tm.resolve_chat(ref)
    except Exception as e:
        await message.answer(f"Не нашёл такой чат: {e}. Пришли ссылку/юзернейм/ID ещё раз.")
        return
    await storage.update(chat_id=chat_id)
    await message.answer(
        f"Чат найден: {title} (id {chat_id}).\n\n"
        "Собрать примеры твоего стиля из истории этого чата автоматически? (да/нет)"
    )
    await state.set_state(Login.style_confirm)


@dp.message(Login.style_confirm, F.text)
@owner_only
async def style_confirm(message: Message, state: FSMContext):
    ans = message.text.strip().lower()
    data = storage.load()
    if ans in ("да", "yes", "y", "д"):
        samples = await tm.collect_recent_own_messages(data["chat_id"])
        await storage.update(style_samples=samples)
        await message.answer(f"Собрал {len(samples)} сообщений для анализа стиля ✅")
    else:
        await message.answer("Ок, стиль можно будет добавить позже командой /style.")
    await message.answer(
        "Настройка завершена. Персонаж начинает отвечать в чате автоматически.\n"
        "Команды: /triggers — триггеры и ссылки, /style — обновить стиль, "
        "/status — статус, /relogin — перелогин."
    )
    await state.clear()
    asyncio.create_task(userbot_runtime.start_listener())


@dp.message(Command("style"))
@owner_only
async def style_cmd(message: Message):
    data = storage.load()
    if not data.get("chat_id"):
        await message.answer("Сначала настрой чат через /relogin.")
        return
    samples = await tm.collect_recent_own_messages(data["chat_id"])
    await storage.update(style_samples=samples)
    await message.answer(f"Обновил примеры стиля: {len(samples)} сообщений.")


@dp.message(Command("setchat"))
@owner_only
async def setchat_cmd(message: Message, state: FSMContext):
    await message.answer("Пришли новую ссылку/username/ID чата.")
    await state.set_state(Login.chat)


# ---------------------------------------------------------------------------
# Триггеры и ссылки — полностью через кнопки
# ---------------------------------------------------------------------------

def _short(text: str, n: int = 28) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def triggers_list_keyboard(triggers: dict) -> InlineKeyboardMarkup:
    rows = []
    for trg_id, trg in triggers.items():
        icon = "🔗" if trg.get("type") == "link" else "📝"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {_short(trg.get('phrase', ''))}",
            callback_data=f"trg:view:{trg_id}",
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить триггер", callback_data="trg:new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trigger_view_keyboard(trg_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Фразу", callback_data=f"trg:editphrase:{trg_id}"),
            InlineKeyboardButton(text="✏️ Ответ/ссылку", callback_data=f"trg:editcontent:{trg_id}"),
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"trg:del:{trg_id}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="trg:back")],
    ])


def type_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Текстовый ответ", callback_data="ttype:text"),
        InlineKeyboardButton(text="🔗 Ссылка", callback_data="ttype:link"),
    ]])


def _triggers_list_text(triggers: dict) -> str:
    if not triggers:
        return (
            "Пока нет ни одного триггера.\n\n"
            "Триггер — это фраза, которая, если встретится в сообщении собеседника, "
            "вызовет фиксированный ответ (текст или ссылку) вместо ответа нейросети.\n"
            "Например: фраза «резюме» → ссылка на файл с резюме."
        )
    return "Твои триггеры и ссылки (нажми, чтобы изменить):"


async def _show_triggers_list(target, edit: bool):
    data = storage.load()
    triggers = data.get("triggers", {})
    text = _triggers_list_text(triggers)
    kb = triggers_list_keyboard(triggers)
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=kb)


@dp.message(Command("triggers"))
@owner_only
async def triggers_cmd(message: Message, state: FSMContext):
    await state.clear()
    await _show_triggers_list(message, edit=False)


@dp.callback_query(F.data == "trg:back")
@owner_only
async def trg_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_triggers_list(call.message, edit=True)
    await call.answer()


@dp.callback_query(F.data.startswith("trg:view:"))
@owner_only
async def trg_view(call: CallbackQuery):
    trg_id = call.data.split(":", 2)[2]
    data = storage.load()
    trg = data.get("triggers", {}).get(trg_id)
    if not trg:
        await call.answer("Уже удалён.", show_alert=True)
        await _show_triggers_list(call.message, edit=True)
        return
    kind = "Ссылка" if trg.get("type") == "link" else "Текстовый ответ"
    text = (
        f"Фраза: «{trg['phrase']}»\n"
        f"Тип: {kind}\n"
        f"Содержимое: {trg['content']}"
    )
    await call.message.edit_text(text, reply_markup=trigger_view_keyboard(trg_id))
    await call.answer()


@dp.callback_query(F.data == "trg:new")
@owner_only
async def trg_new(call: CallbackQuery, state: FSMContext):
    await state.update_data(trg_id=None, field="phrase")
    await state.set_state(TriggerFlow.phrase)
    await call.message.edit_text("Введи фразу-триггер (по какому слову/фразе срабатывать):")
    await call.answer()


@dp.callback_query(F.data.startswith("trg:editphrase:"))
@owner_only
async def trg_editphrase(call: CallbackQuery, state: FSMContext):
    trg_id = call.data.split(":", 2)[2]
    await state.update_data(trg_id=trg_id, field="phrase")
    await state.set_state(TriggerFlow.phrase)
    await call.message.edit_text("Введи новую фразу-триггер:")
    await call.answer()


@dp.callback_query(F.data.startswith("trg:editcontent:"))
@owner_only
async def trg_editcontent(call: CallbackQuery, state: FSMContext):
    trg_id = call.data.split(":", 2)[2]
    await state.update_data(trg_id=trg_id, field="content")
    await state.set_state(TriggerFlow.choose_type)
    await call.message.edit_text("Это будет текстовый ответ или ссылка?", reply_markup=type_choice_keyboard())
    await call.answer()


@dp.callback_query(F.data.startswith("trg:del:"))
@owner_only
async def trg_del(call: CallbackQuery):
    trg_id = call.data.split(":", 2)[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"trg:delyes:{trg_id}"),
        InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"trg:view:{trg_id}"),
    ]])
    await call.message.edit_text("Точно удалить этот триггер?", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("trg:delyes:"))
@owner_only
async def trg_delyes(call: CallbackQuery):
    trg_id = call.data.split(":", 2)[2]
    data = storage.load()
    data.get("triggers", {}).pop(trg_id, None)
    await storage.save(data)
    await call.answer("Удалено")
    await _show_triggers_list(call.message, edit=True)


@dp.message(TriggerFlow.phrase, F.text)
@owner_only
async def trg_phrase_input(message: Message, state: FSMContext):
    phrase = message.text.strip().lower()[:TRIGGER_PHRASE_MAX_LEN]
    if not phrase:
        await message.answer("Фраза не может быть пустой, попробуй ещё раз:")
        return
    fsm_data = await state.get_data()
    trg_id = fsm_data.get("trg_id")

    if trg_id:
        # редактируем только фразу у существующего триггера
        data = storage.load()
        trg = data.get("triggers", {}).get(trg_id)
        if trg:
            trg["phrase"] = phrase
            await storage.save(data)
        await state.clear()
        await message.answer("Фраза обновлена ✅")
        await _show_triggers_list(message, edit=False)
        return

    # создаём новый триггер — дальше спрашиваем тип
    await state.update_data(new_phrase=phrase)
    await state.set_state(TriggerFlow.choose_type)
    await message.answer("Это будет текстовый ответ или ссылка?", reply_markup=type_choice_keyboard())


@dp.callback_query(TriggerFlow.choose_type, F.data.startswith("ttype:"))
@owner_only
async def trg_choose_type(call: CallbackQuery, state: FSMContext):
    trg_type = call.data.split(":", 1)[1]  # text | link
    await state.update_data(trg_type=trg_type)
    await state.set_state(TriggerFlow.content)
    prompt = "Отправь ссылку (например t.me/... или любой URL):" if trg_type == "link" else "Отправь текст ответа:"
    await call.message.edit_text(prompt)
    await call.answer()


@dp.message(TriggerFlow.content, F.text)
@owner_only
async def trg_content_input(message: Message, state: FSMContext):
    content = message.text.strip()[:TRIGGER_CONTENT_MAX_LEN]
    if not content:
        await message.answer("Содержимое не может быть пустым, попробуй ещё раз:")
        return
    fsm_data = await state.get_data()
    trg_id = fsm_data.get("trg_id")
    trg_type = fsm_data.get("trg_type", "text")

    data = storage.load()
    triggers = data.setdefault("triggers", {})

    if trg_id:
        # редактируем ответ/ссылку существующего триггера
        trg = triggers.get(trg_id)
        if trg:
            trg["type"] = trg_type
            trg["content"] = content
    else:
        new_id = uuid.uuid4().hex[:8]
        triggers[new_id] = {
            "phrase": fsm_data.get("new_phrase", ""),
            "type": trg_type,
            "content": content,
        }

    await storage.save(data)
    await state.clear()
    await message.answer("Сохранено ✅")
    await _show_triggers_list(message, edit=False)


# ---------------------------------------------------------------------------

async def notify_owner(text: str):
    if config.OWNER_ID:
        try:
            await bot.send_message(config.OWNER_ID, text)
        except Exception:
            pass


async def run():
    data = storage.load()
    if data["logged_in"] and await tm.is_authorized():
        asyncio.create_task(userbot_runtime.start_listener())
    else:
        await storage.update(logged_in=False)
    await dp.start_polling(bot)
