[21.10.2026 21:25] GRAY: import asyncio
import os
import json
import base64
import aiohttp
from collections import defaultdict

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated, Command
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# ============================================================
# КЛЮЧИ (БЕРУТСЯ ИЗ НАСТРОЕК RENDER)
# ============================================================
MAX_TOKEN = os.environ.get("MAX_TOKEN")
GIGACHAT_KEY = os.environ.get("GIGACHAT_KEY")

# ============================================================
# НАСТРОЙКА
# ============================================================
bot = Bot(token=MAX_TOKEN)
dp = Dispatcher()

giga = GigaChat(
    credentials=GIGACHAT_KEY,
    scope="GIGACHAT_API_PERS",
    verify_ssl_certs=False,
    model="GigaChat-2-Pro"
)

HISTORY_FILE = "histories.json"

# ============================================================
# ЗАГРУЗКА И СОХРАНЕНИЕ ИСТОРИИ
# ============================================================
def load_data():
    if not os.path.exists(HISTORY_FILE):
        return {}, {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            names = {int(k): v for k, v in data.get("names", {}).items()}
            histories = {int(k): v for k, v in data.get("histories", {}).items()}
            return names, histories
    except Exception:
        return {}, {}

def save_data():
    try:
        names_str = {str(k): v for k, v in user_names.items()}
        histories_str = {str(k): v for k, v in user_histories.items()}
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"names": names_str, "histories": histories_str}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

user_names, user_histories = load_data()

SYSTEM_PROMPT = (
    "Ты — школьный учитель. Твоя задача — решать задания и ОБЪЯСНЯТЬ решение пошагово. "
    "Если на фото задание — прочитай его, реши и объясни. Говори по-русски. "
    "КРИТИЧЕСКИ ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать LaTeX и любые команды с обратным слешем. "
    r"Не пиши \frac, \sqrt, \omega, \cdot и другие подобные команды. "
    "Пиши формулы только обычным текстом с помощью доступных символов: пиши '1 / корень(L*C)', "
    "используй знаки умножения (*) и деления (/). Текст решения должен быть понятен школьнику без спецсимволов."
)

# ============================================================
# СКАЧИВАНИЕ ФОТО ИЗ MAX
# ============================================================
async def download_max_photo(photo_url: str, filename: str) -> bool:
    try:
        headers = {"Authorization": f"Bearer {MAX_TOKEN}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url, headers=headers) as response:
                if response.status == 200:
                    with open(filename, "wb") as f:
                        f.write(await response.read())
                    return True
                else:
                    print(f"[ERROR] MAX вернул код {response.status}")
    except Exception as e:
        print(f"[ERROR] Не удалось скачать фото: {e}")
    return False

# ============================================================
# ФУНКЦИЯ ОТВЕТА ЧЕРЕЗ GIGACHAT (С ФОТО)
# ============================================================
async def ask_giga(user_id: int, text: str = None, photo_url: str = None) -> str:
    history = user_histories.get(user_id, [])[-10:]
    
    messages = [Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT)]
    
    if user_id in user_names and user_names[user_id]:
        messages.append(Messages(role=MessagesRole.SYSTEM, content=f"Пользователя зовут {user_names[user_id]}."))
        
    for msg in history:
        role = MessagesRole.USER if msg["role"] == "user" else MessagesRole.ASSISTANT
        messages.append(Messages(role=role, content=msg["content"]))
[21.10.2026 21:25] GRAY: temp_file = None
    try:
        if photo_url:
            temp_file = f"temp_{user_id}.jpg"
            success = await download_max_photo(photo_url, temp_file)
            if success:
                with open(temp_file, "rb") as f:
                    uploaded_file = await asyncio.to_thread(giga.upload_file, f)
                
                messages.append(Messages(
                    role=MessagesRole.USER, 
                    content=text or "Реши задание на фото.", 
                    attachments=[uploaded_file.id_]
                ))
            else:
                return "Не удалось скачать фото. Попробуй ещё раз."
        else:
            messages.append(Messages(role=MessagesRole.USER, content=text))

        print(f"[DEBUG] Отправляю запрос в GigaChat...")
        chat = Chat(messages=messages)
        response = await asyncio.wait_for(asyncio.to_thread(giga.chat, chat), timeout=60.0)
        
        answer = response.choices[0].message.content

        # Очистка от LaTeX
        answer = answer.replace("\\[", "")
        answer = answer.replace("\\]", "")
        answer = answer.replace("$$", "")
        answer = answer.replace("$", "")
        answer = answer.replace("\\frac", " / ")
        answer = answer.replace("\\sqrt", "корень ")
        answer = answer.replace("\\cdot", " * ")
        answer = answer.replace("\\times", " * ")
        answer = answer.replace("\\omega", "w")
        answer = answer.replace("\\pi", "пи")
        answer = answer.replace("\\cos", "cos")
        answer = answer.replace("\\sin", "sin")
        answer = answer.replace("\\text", "")
        answer = answer.replace("\\rm", "")
        answer = answer.replace("{", "")
        answer = answer.replace("}", "")
        answer = answer.replace("###", "")
        answer = answer.replace("##", "")
        answer = answer.replace("#", "")
        answer = answer.replace("\\", "")

        if user_id not in user_histories:
            user_histories[user_id] = []
        user_histories[user_id].append({"role": "user", "content": text or "[изображение]"})
        user_histories[user_id].append({"role": "assistant", "content": answer})
        save_data()

        return answer

    except asyncio.TimeoutError:
        return "Нейросеть слишком долго думает."
    except Exception as e:
        print(f"[ERROR] Ошибка GigaChat: {e}")
        return f"Прости, ошибка: {e}"
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================
@dp.message_created(Command("start"))
async def start_handler(event: MessageCreated):
    user_id = event.message.sender.user_id
    if user_id in user_names and user_names[user_id]:
        await event.message.answer(f"С возвращением, {user_names[user_id]}! Скидывай задание.")
        return
    await event.message.answer("Привет! Я школьный помощник. 🤖\n\nКак тебя зовут?")
    user_names[user_id] = None 

@dp.message_created()
async def message_handler(event: MessageCreated):
    user_id = event.message.sender.user_id
    
    text = None
    photo_url = None
    
    if event.message.body:
        text = getattr(event.message.body, 'text', None)
        if hasattr(event.message.body, 'attachments') and event.message.body.attachments:
            photo_url = event.message.body.attachments[0].payload.url if hasattr(event.message.body.attachments[0], 'payload') else None

    if user_id in user_names and user_names[user_id] is None:
        if text:
            name = text.strip()
            user_names[user_id] = name
            save_data()
            await event.message.answer(f"Приятно познакомиться, {name}! Теперь скидывай задания.")
        else:
            await event.message.answer("Пожалуйста, напиши свое имя текстом.")
        return

    if not text and not photo_url:
        await event.message.answer("Я не вижу ни текста, ни картинки. Скинь задание ещё раз.")
        return
[21.10.2026 21:25] GRAY: await event.message.answer("Смотрю задание...")
    answer = await ask_giga(user_id, text=text, photo_url=photo_url)
    await event.message.answer(answer)

# ============================================================
# ЗАПУСК
# ============================================================
async def main():
    print("Бот запущен. Жду сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
