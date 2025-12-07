from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import logging
import sqlite3

# =======================
# Настройки (меняешь только здесь)
API_TOKEN = "8069786583:AAG_xT6ma1HEXDx2unkj4S9aQa82E6DPDAw"  # токен бота BotFather
ADMIN_IDS = [1906215858, 5517078006]  # ID админов
CLAN_LINK = "https://t.me/+NdQo8-ZoTZJlZWRi"  # ссылка на клан
# =======================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# =======================
# SQLite база
conn = sqlite3.connect("applications.db")
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

# =======================
# Вопросы анкеты по шагам
questions = [
    ("Введите ваше имя:", "user_name"),
    ("Введите город:", "user_city"),
    ("Введите дату рождения (дд.мм.гггг):", "user_birthday"),
    ("Введите ваше семейное положение:", "user_family_status"),
    ("Заинтересованы ли вы в общении с кланом и участии в турнирах? (Да/Нет):", "user_interest"),
    ("Ваш средний онлайн за неделю (часы):", "user_online"),
    ("Опыт игры (лет/месяцев):", "user_experience"),
    ("Ваш ID и Nickname в PUBG:", "user_pubg_id"),
    ("Напишите короткий комментарий о себе:", "user_comment"),
]

# =======================
# Вспомогательные функции
def get_app(user_id):
    cursor.execute("SELECT * FROM applications WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row:
        return dict(zip([c[0] for c in cursor.description], row))
    return None


def save_step(user_id, step):
    cursor.execute(
        "INSERT OR IGNORE INTO applications(user_id, username, step, status) VALUES(?,?,?,?)",
        (user_id, None, step, "pending")
    )
    cursor.execute("UPDATE applications SET step=? WHERE user_id=?", (step, user_id))
    conn.commit()


def save_answer(user_id, key, value):
    cursor.execute(f"UPDATE applications SET {key}=? WHERE user_id=?", (value, user_id))
    conn.commit()


def save_username(user_id, username):
    cursor.execute("UPDATE applications SET username=? WHERE user_id=?", (username, user_id))
    conn.commit()


# =======================
# /start — начало анкеты
@dp.message_handler(commands=['start'])
async def start_application(message: types.Message):
    user_id = message.from_user.id
    save_username(user_id, message.from_user.username or "Нет username")

    if not get_app(user_id):
        save_step(user_id, 0)

    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Анкеты", callback_data="show_public")
    )

    await message.answer(
        "Привет! Начнём заполнение анкеты.\n" + questions[0][0],
        reply_markup=keyboard
    )


# =======================
# Получение ответов
@dp.message_handler()
async def process_answer(message: types.Message):
    user_id = message.from_user.id
    app = get_app(user_id)

    if not app:
        return

    step = app["step"]
    key = questions[step][1]

    save_answer(user_id, key, message.text)

    step += 1
    save_step(user_id, step)

    if step < len(questions):
        await message.answer(questions[step][0])
    else:
        # формирование заявки
        app = get_app(user_id)
        text = f"Новая заявка от @{app['username']} (ID: {user_id})"

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Принять", callback_data=f"accept_{user_id}"),
            InlineKeyboardButton("Отклонить", callback_data=f"reject_{user_id}"),
            InlineKeyboardButton("Показать приватную анкету", callback_data=f"show_private_{user_id}")
        )

        for admin in ADMIN_IDS:
            await bot.send_message(admin, text, reply_markup=keyboard)

        await message.answer("Анкета отправлена администраторам!")


# =======================
# Обработка кнопок админов
@dp.callback_query_handler(lambda c: c.data.startswith(("accept_", "reject_", "show_private_")))
async def process_admin(callback_query: types.CallbackQuery):
    data = callback_query.data
    user_id = int(data.split("_")[-1])
    app = get_app(user_id)

    if not app:
        await callback_query.answer("Анкета не найдена")
        return

    # ===== принятие =====
    if data.startswith("accept_"):
        cursor.execute("UPDATE applications SET status='accepted' WHERE user_id=?", (user_id,))
        conn.commit()

        await bot.send_message(
            user_id,
            f"Поздравляем, {app['user_name']}! Ваша заявка принята.\nСсылка на клан: {CLAN_LINK}"
        )

        public_text = f"Публичная анкета @{app['username']}:\n\n"
        for q_text, q_key in questions:
            if q_key not in ["user_city", "user_experience"]:
                public_text += f"{q_text} {app[q_key]}\n"

        for admin in ADMIN_IDS:
            await bot.send_message(admin, public_text)

        await callback_query.answer("Заявка принята")

    # ===== отклонение =====
    elif data.startswith("reject_"):
        cursor.execute("UPDATE applications SET status='rejected' WHERE user_id=?", (user_id,))
        conn.commit()

        await bot.send_message(
            user_id,
            f"К сожалению, {app['user_name']}, ваша заявка отклонена."
        )

        await callback_query.answer("Заявка отклонена")

    # ===== показать приватную анкету =====
    elif data.startswith("show_private_"):
        private_text = "Приватная анкета:\n\n" + "\n".join(
            f"{q_text} {app[q_key]}" for q_text, q_key in questions
        )

        await callback_query.message.answer(private_text)
        await callback_query.answer("Приватная анкета показана")


# =======================
# Показ публичных анкет пользователям
@dp.callback_query_handler(lambda c: c.data == "show_public")
async def show_public(callback_query: types.CallbackQuery):
    cursor.execute("SELECT * FROM applications WHERE status='accepted'")
    rows = cursor.fetchall()

    if not rows:
        await callback_query.message.answer("Пока нет опубликованных анкет.")
        return

    for row in rows:
        app = dict(zip([col[0] for col in cursor.description], row))

        public_text = f"Публичная анкета @{app['username']}:\n\n"
        for q_text, q_key in questions:
            if q_key not in ["user_city", "user_experience"]:
                public_text += f"{q_text} {app[q_key]}\n"

        await callback_query.message.answer(public_text)

    await callback_query.answer()


# =======================
# Старт бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
            
