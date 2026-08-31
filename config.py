import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота-помощника (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# api_id / api_hash — получить на https://my.telegram.org (раздел "API development tools")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# Бесплатный ключ Groq — получить на https://console.groq.com/keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Твой Telegram user_id (узнать у @userinfobot). Только этот пользователь
# сможет управлять ботом-помощником.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

SESSION_NAME = os.getenv("SESSION_NAME", "persona_session")
DATA_FILE = os.getenv("DATA_FILE", "data/storage.json")

# Порт для веб-сервера keep-alive (Render сам подставляет PORT для web-сервисов)
PORT = int(os.getenv("PORT", "10000"))
