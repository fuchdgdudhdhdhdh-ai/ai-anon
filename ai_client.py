from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL
from local_settings import (
    SYSTEM_PROMPT_TEMPLATE,
    GROQ_TEMPERATURE,
    GROQ_MAX_TOKENS,
    HISTORY_MESSAGES,
    STYLE_SAMPLES_IN_PROMPT,
)

_client = Groq(api_key=GROQ_API_KEY)


def build_system_prompt(persona_name: str, style_samples: list) -> str:
    prompt = SYSTEM_PROMPT_TEMPLATE.format(persona_name=persona_name)
    if style_samples:
        examples = "\n".join(f"- {s}" for s in style_samples[:STYLE_SAMPLES_IN_PROMPT])
        prompt += (
            "\n\nПримеры реальных сообщений владельца "
            "(ориентируйся на стиль, тон, длину фраз, лексику):\n" + examples
        )
    return prompt


def generate_reply(system_prompt: str, history: list, user_message: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_message})

    completion = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
    )
    return completion.choices[0].message.content.strip()
