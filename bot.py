import os
import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command

# ==========================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ==========================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # токен бота
GROUP_LINK = os.getenv("GROUP_LINK")  # ссылка на группу клана
ADMINS = list(map(int, os.getenv("ADMINS").split(",")))  # ID админов через запятую

# ==========================
# ЛОГИ
# ==========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ==========================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ==========================
# БАЗА ДАННЫХ
# ==========================
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
    user_pubg_id TEXT,
    status TEXT
)
""")
conn.commit()

# ==========================
# ВОПРОСЫ АНКЕТЫ
# ==========================
questions = [
    ("Введите ваше имя:", "user_name"),
    ("Введите город:", "user_city"),  # приватное
    ("Введите дату рождения (дд.мм.гггг):", "user_birthday"),
    ("Ваше семейное положение:", "user_family_status"),
    ("Будете участвовать в общении и турнирах? (Да/Нет):", "user_interest"),
    ("Средний онлайн за неделю (часы):", "user_online"),
    ("Ваш ID и Nickname в PUBG:", "user_pubg_id"),
]
PRIVATE_FIELDS = {"user_city"}

# ==========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================
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

def delete_app(uid):
    cursor.execute("DELETE FROM applications WHERE user_id=?", (uid,))
    conn.commit()

# ==========================
# ГЛАВНОЕ МЕНЮ
# ==========================
def main_menu(uid):
    app = get_app(uid)
    buttons = []
    if not app or app["status"] == "rejected" or app["status"] == "pending":
        buttons.append([types.InlineKeyboardButton("Заполнить анкету", callback_data="fill")])
    buttons.append([types.InlineKeyboardButton("Анкеты", callback_data="show_public")])
    if app and app["status"] == "accepted":
        buttons.append([types.InlineKeyboardButton("Моя анкета", callback_data="my_app")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    ensure(message.from_user.id, message.from_user.username or "Нет username")
    await message.answer("Главное меню:", reply_markup=main_menu(message.from_user.id))

# ==========================
# ЗАПОЛНЕНИЕ АНКЕТЫ
# ==========================
@router.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    data = callback.data
    uid = callback.from_user.id

    # Главное меню: Заполнить анкету
    if data == "fill":
        ensure(uid, callback.from_user.username or "Нет username")
        cursor.execute("UPDATE applications SET step=0, status='pending' WHERE user_id=?", (uid,))
        conn.commit()
        await callback.message.answer(questions[0][0])
        await callback.answer()
        return

    # Публичные анкеты
    if data == "show_public":
        cursor.execute("SELECT * FROM applications WHERE status='accepted'")
        rows = cursor.fetchall()
        if not rows:
            await callback.message.answer("Публичных анкет пока нет.")
            return await callback.answer()
        for row in rows:
            app = dict(zip([c[0] for c in cursor.description], row))
            lines = [f"Публичная анкета @{app['username']}:\n"]
            for q_text, key in questions:
                if key in PRIVATE_FIELDS:
                    continue
                lines.append(f"{q_text} {app.get(key,'')}")
            await callback.message.answer("\n".join(lines))
        await callback.answer()
        return

    # Моя анкета
    if data == "my_app":
        app = get_app(uid)
        if not app:
            await callback.answer("У вас нет анкеты", show_alert=True)
            return
        lines = ["Ваша анкета:\n"]
        for q_text, key in questions:
            lines.append(f"{q_text} {app.get(key,'')}")
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton("Удалить анкету", callback_data="delete_my")]
        ])
        await callback.message.answer("\n".join(lines), reply_markup=kb)
        await callback.answer()
        return

    # Удаление анкеты
    if data == "delete_my":
        delete_app(uid)
        await callback.message.answer("Ваша анкета удалена.")
        await callback.message.answer("Главное меню:", reply_markup=main_menu(uid))
        await callback.answer()
        return

    # --- ОТВЕТЫ АНКЕТЫ ---
    app = get_app(uid)
    if app and app["step"] < len(questions):
        q_text, q_key = questions[app["step"]]
        save_answer(uid, q_key, callback.data)
        step = app["step"] + 1
        save_step(uid, step)
        if step < len(questions):
            await callback.message.answer(questions[step][0])
        else:
            # Анкета заполнена → отправляем админам
            app = get_app(uid)
            user_info = f"Заявка от @{app['username']} (ID: {uid})"
            private_lines = ["Приватная анкета:\n"]
            for q_text, k in questions:
                private_lines.append(f"{q_text} {app.get(k,'')}")
            kb_admin = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton("Принять", callback_data=f"accept_{uid}"),
                    types.InlineKeyboardButton("Отклонить", callback_data=f"reject_{uid}")
                ],
                [
                    types.InlineKeyboardButton("Показать приватную", callback_data=f"show_private_{uid}")
                ]
            ])
            for admin in ADMINS:
                try:
                    await bot.send_message(admin, user_info)
                    await bot.send_message(admin, "\n".join(private_lines), reply_markup=kb_admin)
                except:
                    pass
            await callback.message.answer("Анкета отправлена администраторам!")
        await callback.answer()
        return

    # --- АДМИН ---
    if uid not in ADMINS:
        return

    # Приватная анкета
    if data.startswith("show_private_"):
        target_id = int(data.split("_")[2])
        app = get_app(target_id)
        lines = ["Приватная анкета:\n"]
        for q_text, key in questions:
            lines.append(f"{q_text} {app.get(key,'')}")
        await callback.message.answer("\n".join(lines))
        await callback.answer()
        return

    # Принять
    if data.startswith("accept_"):
        target_id = int(data.split("_")[1])
        set_status(target_id, "accepted")
        app = get_app(target_id)
        try:
            await bot.send_message(target_id, f"🎉 Ваша анкета принята!\nВступайте в группу: {GROUP_LINK}")
        except:
            pass
        # Публичная версия админам
        lines = [f"Публичная анкета @{app['username']}:\n"]
        for q_text, key in questions:
            if key not in PRIVATE_FIELDS:
                lines.append(f"{q_text} {app.get(key,'')}")
        for admin in ADMINS:
            try:
                await bot.send_message(admin, "\n".join(lines))
            except:
                pass
        await callback.answer("Принято!")
        return

    # Отклонить
    if data.startswith("reject_"):
        target_id = int(data.split("_")[1])
        set_status(target_id, "rejected")
        try:
            await bot.send_message(target_id, "❌ Ваша анкета отклонена.")
        except:
            pass
        await callback.answer("Отклонено!")
        return

# ==========================
# ПРОСЛУШКА ТЕКСТА (пошаговая анкета)
# ==========================
@router.message()
async def process_text(message: types.Message):
    uid = message.from_user.id
    app = get_app(uid)
    if app and app["step"] < len(questions):
        q_text, q_key = questions[app["step"]]
        save_answer(uid, q_key, message.text)
        step = app["step"] + 1
        save_step(uid, step)
        if step < len(questions):
            await message.answer(questions[step][0])
        else:
            # Анкета заполнена → отправляем админам
            app = get_app(uid)
            user_info = f"Заявка от @{app['username']} (ID: {uid})"
            private_lines = ["Приватная анкета:\n"]
            for q_text, k in questions:
                private_lines.append(f"{q_text} {app.get(k,'')}")
            kb_admin = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton("Принять", callback_data=f"accept_{uid}"),
                    types.InlineKeyboardButton("Отклонить", callback_data=f"reject_{uid}")
                ],
                [
                    types.InlineKeyboardButton("Показать приватную", callback_data=f"show_private_{uid}")
                ]
            ])
            for admin in ADMINS:
                try:
                    await bot.send_message(admin, user_info)
                    await bot.send_message(admin, "\n".join(private_lines), reply_markup=kb_admin)
                except:
                    pass
            await message.answer("Анкета отправлена администраторам!")

# ==========================
# ЗАПУСК БОТА
# ==========================
async def main():
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
