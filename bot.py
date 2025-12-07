import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# =======================
# Настройки (меняешь только здесь)
API_TOKEN = "8069786583:AAG_xT6ma1HEXDx2unkj4S9aQa82E6DPDAw"
ADMIN_IDS = [1906215858, 5517078006]  # список numeric ID админов
CLAN_LINK = "https://t.me/+NdQo8-ZoTZJlZWRi"
# =======================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# =======================
# База данных (sqlite)
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

# =======================
# Вопросы анкеты (порядок важен)
questions = [
    ("Введите ваше имя:", "user_name"),
    ("Введите город:", "user_city"),  # приватное поле
    ("Введите дату рождения (дд.мм.гггг):", "user_birthday"),
    ("Введите ваше семейное положение:", "user_family_status"),
    ("Заинтересованы ли вы в общении с кланом и участии в турнирах? (Да/Нет):", "user_interest"),
    ("Ваш средний онлайн за неделю (часы):", "user_online"),
    ("Опыт игры (лет/месяцев):", "user_experience"),  # приватное поле
    ("Ваш ID и Nickname в PUBG:", "user_pubg_id"),
    ("Напишите короткий комментарий о себе:", "user_comment"),
]

# Поля, которые должны быть скрыты в публичной версии
PRIVATE_FIELDS = {"user_city", "user_experience"}


# =======================
# Вспомогательные функции для работы с БД
def get_app(user_id: int):
    cursor.execute("SELECT * FROM applications WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row:
        return dict(zip([c[0] for c in cursor.description], row))
    return None


def ensure_app_row(user_id: int, username: str | None):
    """Создать строку при первом /start"""
    cursor.execute(
        "INSERT OR IGNORE INTO applications(user_id, username, step, status) VALUES(?,?,?,?)",
        (user_id, username or "Нет username", 0, "pending"),
    )
    cursor.execute("UPDATE applications SET username=? WHERE user_id=?", (username or "Нет username", user_id))
    conn.commit()


def save_step(user_id: int, step: int):
    cursor.execute("UPDATE applications SET step=? WHERE user_id=?", (step, user_id))
    conn.commit()


def save_answer(user_id: int, key: str, value: str):
    cursor.execute(f"UPDATE applications SET {key}=? WHERE user_id=?", (value, user_id))
    conn.commit()


def set_status(user_id: int, status: str):
    cursor.execute("UPDATE applications SET status=? WHERE user_id=?", (status, user_id))
    conn.commit()


# =======================
# /start — начало анкеты
@dp.message.register(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    ensure_app_row(user_id, username)

    # Кнопка "Анкеты" — показывает публичные принятые анкеты
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("Анкеты", callback_data="show_public"))

    # Начинаем с первого вопроса (step хранится в БД)
    app = get_app(user_id)
    step = app["step"] if app else 0
    # Если пользователь уже заполнил анкету (step >= len), сообщаем и предложим повторить
    if step >= len(questions):
        await message.answer("Вы уже заполнили анкету. Если хотите заполнить заново, отправьте /start снова.")
        return

    await message.answer(questions[0][0], reply_markup=markup)


# =======================
# Универсальный хэндлер для всех текстовых сообщений — используем step из БД
@dp.message.register()
async def all_messages_handler(message: types.Message):
    user_id = message.from_user.id
    app = get_app(user_id)
    if not app:
        # попросим начать /start
        await message.answer("Нажмите /start, чтобы начать заполнение анкеты.")
        return

    step = app.get("step", 0)
    # Если анкета уже завершена — игнорируем обычные сообщения
    if step >= len(questions):
        await message.answer("Анкета уже заполнена. Ждите решения админов.")
        return

    # Сохраняем ответ на текущий вопрос
    q_text, q_key = questions[step]
    save_answer(user_id, q_key, message.text)

    # Переходим к следующему вопросу
    step += 1
    save_step(user_id, step)

    if step < len(questions):
        await message.answer(questions[step][0])
    else:
        # Анкета завершена — отправляем сообщения админам
        app = get_app(user_id)  # обновлённая запись
        # 1) Отдельное сообщение с информацией о пользователе (username и id)
        info_text = f"Заявка от @{app['username']} (ID: {user_id})"
        # 2) Приватная анкета — все поля, только для админов, с кнопками
        private_lines = []
        for q_text, q_key in questions:
            value = app.get(q_key) or ""
            private_lines.append(f"{q_text} {value}")
        private_text = "Приватная анкета:\n\n" + "\n".join(private_lines)

        # Кнопки для админов: Принять, Отклонить, Показать приватную
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Принять", callback_data=f"accept_{user_id}"),
            InlineKeyboardButton("Отклонить", callback_data=f"reject_{user_id}"),
            InlineKeyboardButton("Показать приватную анкету", callback_data=f"show_private_{user_id}"),
        )

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, info_text)
                await bot.send_message(admin_id, private_text, reply_markup=keyboard)
            except Exception as e:
                logger.exception("Не удалось отправить админу %s: %s", admin_id, e)

        await message.answer("Анкета отправлена администраторам. Ожидайте решения.")


# =======================
# Callback: принятие/отклонение/показ приватной анкеты
@dp.callback_query.register()
async def callback_handler(callback: types.CallbackQuery):
    data = callback.data or ""
    # show_public handled elsewhere
    if data == "show_public":
        # Показать все публичные принятые анкеты (status='accepted')
        cursor.execute("SELECT * FROM applications WHERE status='accepted'")
        rows = cursor.fetchall()
        if not rows:
            await callback.message.answer("Пока нет опубликованных анкет.")
            await callback.answer()
            return

        for row in rows:
            app = dict(zip([c[0] for c in cursor.description], row))
            public_lines = []
            public_lines.append(f"Публичная анкета @{app['username']}:")
            for q_text, q_key in questions:
                if q_key in PRIVATE_FIELDS:
                    continue
                value = app.get(q_key) or ""
                public_lines.append(f"{q_text} {value}")
            await callback.message.answer("\n".join(public_lines))
        await callback.answer()
        return

    # Admin actions: accept_, reject_, show_private_
    if data.startswith(("accept_", "reject_", "show_private_")):
        parts = data.split("_")
        action = parts[0]
        try:
            target_user_id = int(parts[-1])
        except ValueError:
            await callback.answer("Неверный ID в callback.")
            return

        # Проверка: только админы могут использовать эти кнопки
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("Только администраторы могут нажимать эту кнопку.", show_alert=True)
            return

        app = get_app(target_user_id)
        if not app:
            await callback.answer("Анкета не найдена.")
            return

        if action == "accept":
            set_status(target_user_id, "accepted")
            # Отправляем игроку уведомление и ссылку
            try:
                await bot.send_message(
                    target_user_id,
                    f"Поздравляем, {app.get('user_name','игрок')}! Ваша заявка принята.\nСсылка на клан: {CLAN_LINK}"
                )
            except Exception as e:
                logger.exception("Не удалось отправить сообщение пользователю %s: %s", target_user_id, e)

            # Формируем публичную версию (скрываем приватные поля) — бот хранит их в БД и покажет по кнопке "Анкеты"
            public_lines = [f"Публичная анкета @{app['username']}:"]
            for q_text, q_key in questions:
                if q_key in PRIVATE_FIELDS:
                    continue
                public_lines.append(f"{q_text} {app.get(q_key,'')}")
            public_text = "\n".join(public_lines)

            # По умолчанию шлём публичную версию админам (можно заменить на отправку в общий канал)
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, public_text)
                except Exception:
                    pass

            await callback.answer("Заявка принята")

        elif action == "reject":
            set_status(target_user_id, "rejected")
            try:
                await bot.send_message(
                    target_user_id,
                    f"К сожалению, {app.get('user_name','игрок')}, ваша заявка отклонена."
                )
            except Exception:
                pass
            await callback.answer("Заявка отклонена")

        elif action == "show_private":
            # Показываем приватную анкету прямо в чате админа
            private_lines = []
            for q_text, q_key in questions:
                private_lines.append(f"{q_text} {app.get(q_key,'')}")
            await callback.message.answer("Приватная анкета:\n\n" + "\n".join(private_lines))
            await callback.answer("Приватная анкета показана")

        return

    # default
    await callback.answer()


# =======================
# Запуск бота (aiogram 3 style)
async def main():
    # перед стартом можно выполнить проверку БД или другие init-действия
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # закрыть соединение с БД корректно
        conn.close()
                             
