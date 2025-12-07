import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command

# ========= НАСТРОЙКИ =========
API_TOKEN = "8069786583:AAG_xT6ma1HEXDx2unkj4S9aQa82E6DPDAw"
ADMIN_IDS = [1906215858, 5517078006]
CLAN_LINK = "https://t.me/+NdQo8-ZoTZJlZWRi"
# =============================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ========= БАЗА ДАННЫХ =========
conn = sqlite3.connect("applications.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS applications (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    step INTEGER,
    user_name TEXT,
    user_city TEXT,
    user_birthday TEXT,
    user_family_status TEXT,
    user_interest TEXT,
    user_online TEXT,
    user_experience TEXT,
    user_pubg_id TEXT,
    user_comment TEXT,
    status TEXT
)
""")
conn.commit()

# ========= ВОПРОСЫ =========
questions = [
    ("Введите ваше имя:", "user_name"),
    ("Введите город:", "user_city"),  # приватное
    ("Введите дату рождения (дд.мм.гггг):", "user_birthday"),
    ("Ваше семейное положение:", "user_family_status"),
    ("Будете участвовать в общении и турнирах? (Да/Нет):", "user_interest"),
    ("Средний онлайн за неделю (часы):", "user_online"),
    ("Опыт игры:", "user_experience"),  # приватное
    ("Ваш ID и Nickname в PUBG:", "user_pubg_id"),
    ("Комментарий о себе:", "user_comment"),
]

PRIVATE_FIELDS = {"user_city", "user_experience"}

# ========= HELPERS =========

def get_app(uid):
    cursor.execute("SELECT * FROM applications WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    return dict(zip([c[0] for c in cursor.description], row)) if row else None

def ensure(uid, username):
    cursor.execute(
        "INSERT OR IGNORE INTO applications(user_id, username, step, status) VALUES (?, ?, ?, ?)",
        (uid, username, 0, "pending")
    )
    cursor.execute("UPDATE applications SET username=? WHERE user_id=?", (username, uid))
    conn.commit()

def save_step(uid, step):
    cursor.execute("UPDATE applications SET step=? WHERE user_id=?", (step, uid))
    conn.commit()

def save_answer(uid, key, val):
    cursor.execute(f"UPDATE applications SET {key}=? WHERE user_id=?", (val, uid))
    conn.commit()

def set_status(uid, status):
    cursor.execute("UPDATE applications SET status=? WHERE user_id=?", (status, uid))
    conn.commit()


# ========= /start =========

@router.message(Command("start"))
async def start(message: types.Message):
    uid = message.from_user.id
    ensure(uid, message.from_user.username or "Нет username")

    app = get_app(uid)
    step = app["step"]

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Анкеты", callback_data="show_public")]
        ]
    )

    await message.answer(questions[0][0], reply_markup=keyboard)


# ========= Получение ответов =========

@router.message(F.text)
async def process(message: types.Message):
    uid = message.from_user.id
    app = get_app(uid)
    if not app:
        return await message.answer("Нажмите /start, чтобы начать.")

    step = app["step"]
    if step >= len(questions):
        return await message.answer("Анкета уже заполнена, ожидайте решения.")

    q_text, q_key = questions[step]
    save_answer(uid, q_key, message.text)

    step += 1
    save_step(uid, step)

    if step < len(questions):
        await message.answer(questions[step][0])
    else:
        # АНКЕТА ЗАКОНЧЕНА → отправляем админам
        app = get_app(uid)

        user_info = f"Заявка от @{app['username']} (ID: {uid})"
        private = ["Приватная анкета:\n"]
        for q_text, k in questions:
            private.append(f"{q_text} {app.get(k,'')}")

        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="Принять", callback_data=f"accept_{uid}"),
                    types.InlineKeyboardButton(text="Отклонить", callback_data=f"reject_{uid}")
                ],
                [
                    types.InlineKeyboardButton(text="Показать приватную", callback_data=f"show_private_{uid}")
                ]
            ]
        )

        for admin in ADMIN_IDS:
            try:
                await bot.send_message(admin, user_info)
                await bot.send_message(admin, "\n".join(private), reply_markup=kb)
            except:
                pass

        await message.answer("Анкета отправлена админам!")


# ========= Callback-кнопки =========

@router.callback_query(F.data == "show_public")
async def show_public(callback: types.CallbackQuery):
    cursor.execute("SELECT * FROM applications WHERE status='accepted'")
    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("Публичных анкет пока нет.")
        return await callback.answer()

    for row in rows:
        app = dict(zip([c[0] for c in cursor.description], row))
        text = [f"Публичная анкета @{app['username']}:\n"]
        for q_text, key in questions:
            if key in PRIVATE_FIELDS:
                continue
            text.append(f"{q_text} {app.get(key,'')}")
        await callback.message.answer("\n".join(text))

    await callback.answer()


@router.callback_query(F.data.startswith("show_private_"))
async def show_private(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[2])
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("Недоступно", show_alert=True)

    app = get_app(uid)

    text = ["Приватная анкета:\n"]
    for q_text, key in questions:
        text.append(f"{q_text} {app.get(key,'')}")

    await callback.message.answer("\n".join(text))
    await callback.answer()


@router.callback_query(F.data.startswith("accept_"))
async def accept(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("Недоступно", show_alert=True)

    set_status(uid, "accepted")
    app = get_app(uid)

    await bot.send_message(uid, f"Поздравляем! Ваша заявка принята.\nСсылка: {CLAN_LINK}")

    # отправляем публичную версию в личные анкеты
    text = [f"Публичная анкета @{app['username']}:\n"]
    for q_text, key in questions:
        if key not in PRIVATE_FIELDS:
            text.append(f"{q_text} {app.get(key,'')}")

    for admin in ADMIN_IDS:
        await bot.send_message(admin, "\n".join(text))

    await callback.answer("Принято!")


@router.callback_query(F.data.startswith("reject_"))
async def reject(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("Недоступно", show_alert=True)

    set_status(uid, "rejected")
    await bot.send_message(uid, "К сожалению, ваша заявка отклонена.")
    await callback.answer("Отклонено!")


# ========= Запуск =========

async def main():
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
              
