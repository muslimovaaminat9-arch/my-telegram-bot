import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq

# ----------------- НАСТРОЙКИ -----------------
BOT_TOKEN = "8612753024:AAHwtgbPWIy2J3DlmpNxLrdPQPjmkw4IqKg"
GROQ_API_KEY = "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"
CHANNEL_ID = "@aiconfe"
ADMIN_ID = 8665906161
MODERATION_GROUP_ID = -1004417481682
PROXY_URL = "http://proxy.server:3128"
# ----------------------------------------------

# Подключаем прокси PythonAnywhere для бота
session = AiohttpSession(proxy=PROXY_URL)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)
scheduler = AsyncIOScheduler()

pending_replies = {}

def init_db():
    conn = sqlite3.connect("confessions.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def register_user(user_id: int):
    conn = sqlite3.connect("confessions.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def save_post(text: str):
    conn = sqlite3.connect("confessions.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO posts (text) VALUES (?)", (text,))
    conn.commit()
    conn.close()

# Функция получения случайной картинки котика (через прокси)
async def get_random_cat_url():
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get("https://api.thecatapi.com/v1/images/search", proxy=PROXY_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data[0]["url"]
    except Exception as e:
        print(f"Ошибка получения котика: {e}")
    return None

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        register_user(message.from_user.id)
        welcome_text = (
            "𝅄 。wᧉlcꝍmᧉ ⎯ּ. ⏕ \n"
            "      【 ֺбот принадлежит — @aiconfe ❱\n"
            "   ( ⁠⁠⁠⁠⁠ ⁠⁠⁠ ᷼ . 𝆬. Здесь ты можешь поделиться со всем, что как-либо связано с ИИ. "
            "Начиная с ошибок, заканчивая до обсуждения каких-либо приколов или же рекламой своих ботов в tavo/janitor/ST. ) 、"
        )
        await message.answer(welcome_text)

# --- ОТВЕТ АДМИНА В ГРУППЕ (REPLY) ---
@dp.message(F.reply_to_message)
async def admin_reply_in_group(message: types.Message):
    if message.chat.id != MODERATION_GROUP_ID:
        return

    replied_msg = message.reply_to_message
    target_user_id = pending_replies.get(replied_msg.message_id)

    if not target_user_id and replied_msg.text and "ID:" in replied_msg.text:
        try:
            target_user_id = int(replied_msg.text.split("ID:")[1].strip())
        except Exception:
            pass

    if target_user_id:
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text=f"💬 <b>Ответ от администрации:</b>\n\n{message.text}",
                parse_mode=ParseMode.HTML
            )
            await message.reply("✅ Ответ успешно отправлен автору в ЛС!")
        except Exception as e:
            await message.reply(f"❌ Ошибка отправки: {e}")
    else:
        await message.reply("⚠️ Не удалось определить автора этой предложки (возможно, бот перезапускался).")

# --- ОБРАБОТКА ПРЕДЛОЖКИ ---
@dp.message(F.chat.type == "private", F.text & ~F.command)
async def handle_suggestion(message: types.Message):
    register_user(message.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data="reject")]
    ])
    
    try:
        msg_text = (
            f"📥 <b>Новая предложка:</b>\n\n"
            f"{message.text}\n\n"
            f"<i>(Сделайте Reply на это сообщение, чтобы ответить)</i>\n"
            f"<tg-spoiler>ID:{message.from_user.id}</tg-spoiler>"
        )
        
        sent_msg = await bot.send_message(
            chat_id=MODERATION_GROUP_ID,
            text=msg_text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )
        pending_replies[sent_msg.message_id] = message.from_user.id

        # Отправляем случайную фотку котика
        cat_url = await get_random_cat_url()
        caption_text = "Ваше признание отправлено на модерацию! 🤫"

        if cat_url:
            await message.answer_photo(photo=cat_url, caption=caption_text)
        else:
            await message.answer(caption_text)

    except Exception as e:
        print(f"❌ ОШИБКА ОТПРАВКИ В ГРУППУ: {e}")
        await message.answer(f"⚠️ Ошибка отправки на модерацию в группу: {e}")

# --- КНОПКИ МОДЕРАЦИИ ---
@dp.callback_query(F.data.in_({"publish", "reject"}))
async def admin_decision(callback: types.CallbackQuery):
    if callback.data == "publish":
        text_full = callback.message.text
        if "📥 Новая предложка:" in text_full:
            raw_text = text_full.split("📥 Новая предложка:")[1].split("(Сделайте Reply")[0].strip()
        else:
            raw_text = text_full

        formatted_post = (
            f"GF\n\n"
            f"«{raw_text}»\n"
            f"      𓈒  ᷼    ִ  ︶︶ @aiconfe_bot"
        )
        
        await bot.send_message(chat_id=CHANNEL_ID, text=formatted_post)
        save_post(raw_text)
        await callback.message.edit_text(callback.message.text + "\n\n✅ <b>Опубликовано</b>", parse_mode=ParseMode.HTML)
    else:
        await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Отклонено</b>", parse_mode=ParseMode.HTML)

async def main():
    init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
