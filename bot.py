import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= SOZLAMALAR =================
BOT_TOKEN = "9238053109:AAHWwYeZHpqwxISCDvPye_4tRvePYvFkHH0"
ADMIN_ID = 123456789  # @userinfobot dan olingan ID raqamingiz
WEBAPP_URL = "https://smm-boostuz.netlify.app/"  # index.html joylangan HTTPS havola
# ==============================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Ma'lumotlar bazasi
conn = sqlite3.connect("database.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    balance INTEGER DEFAULT 2,
    referrer_id INTEGER
)
""")
conn.commit()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_coin_user = State()
    waiting_for_coin_amount = State()

# Foydalanuvchini bazaga qo'shish
def register_user(user_id, full_name, ref_id=None):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, full_name, balance, referrer_id) VALUES (?, ?, 2, ?)",
            (user_id, full_name, ref_id)
        )
        conn.commit()
        if ref_id and ref_id != user_id:
            cursor.execute("UPDATE users SET balance = balance + 3 WHERE user_id = ?", (ref_id,))
            conn.commit()
            return True
    return False

# /start buyrug'i
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    ref_id = int(command.args) if (command.args and command.args.isdigit()) else None
    is_new_ref = register_user(message.from_user.id, message.from_user.full_name, ref_id)

    if is_new_ref:
        try:
            await bot.send_message(ref_id, "🎉 Do'stingiz botga qo'shildi! Sizga +3 tanga berildi.")
        except Exception:
            pass

    # Web App ochish tugmasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Ilovani ochish (Web App)", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

    await message.answer(
        f"👋 Salom, <b>{message.from_user.full_name}</b>!\n\n"
        "Ijtimoiy tarmoqlarda obunachi, layk va prosmotr ko'paytirish uchun "
        "pastdagi <b>Ilovani ochish</b> tugmasini bosing 👇",
        reply_markup=kb,
        parse_mode="HTML"
    )

# ================= ADMIN PANEL =================
def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Hammaga xabar yuborish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💰 Tanga qo'shish / ayirish", callback_data="adm_coins")]
    ])

@dp.message(Command("admin"))
async def open_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠 <b>Admin boshqaruv paneli:</b>", reply_markup=admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats")
async def show_stats(callback: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*), SUM(balance) FROM users")
    total_users, total_coins = cursor.fetchone()
    await callback.message.edit_text(
        f"📊 <b>Bot statistikasi:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n"
        f"🪙 Umumiy tangalar: <b>{total_coins or 0} ta</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "adm_broadcast")
async def ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni yozing (rasm yoki matn):")
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def send_broadcast(message: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await message.copy_to(uid)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Xabar <b>{sent} ta</b> foydalanuvchiga yuborildi!", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "adm_coins")
async def ask_user_id(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_coin_user)
    await callback.message.answer("👤 Foydalanuvchining Telegram ID raqamini yuboring:")
    await callback.answer()

@dp.message(AdminState.waiting_for_coin_user)
async def ask_coin_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Faqat raqam yuboring!")
        return
    await state.update_data(target_id=int(message.text))
    await state.set_state(AdminState.waiting_for_coin_amount)
    await message.answer("💰 Qancha tanga qo'shmoqchisiz? (Ayirish uchun minus bilan yozing, masalan: -50):")

@dp.message(AdminState.waiting_for_coin_amount)
async def update_user_coins(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("⚠️ To'g'ri raqam kiriting!")
        return

    data = await state.get_data()
    target_id = data["target_id"]
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()

    await message.answer(f"✅ Foydalanuvchi (<code>{target_id}</code>) balansiga <b>{amount} tanga</b> o'zgartirildi.", parse_mode="HTML")
    try:
        await bot.send_message(target_id, f"💰 Admin hisobingizni <b>{amount} tanga</b>ga o'zgartirdi!", parse_mode="HTML")
    except Exception:
        pass
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import os
from aiohttp import web

async def health_check(request):
    return web.Response(text="Bot ishlayapti!")

async def main():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
