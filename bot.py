InlineKeyboardButton("Показать приватную анкету", callback_data=f"show_private_{user_id}")
        )
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, info_text, reply_markup=keyboard)
        await message.answer("Ваша анкета отправлена администраторам.")

# -----------------------
# Обработка действий админов
@dp.callback_query_handler(lambda c: c.data.startswith(("accept_", "reject_", "show_private_")))
async def admin_actions(callback_query: types.CallbackQuery):
    data = callback_query.data
    user_id_str = data.split("_")[-1]
    user_id = int(user_id_str)
    app = get_app(user_id)
    if not app:
        await callback_query.answer("Анкета не найдена")
        return

    if data.startswith("accept_"):
        cursor.execute("UPDATE applications SET status='accepted' WHERE user_id=?", (user_id,))
        conn.commit()
        # Отправка игроку
        await bot.send_message(user_id, f"Поздравляем, {app['user_name']}! Ваша заявка принята.\nСсылка на клан: {CLAN_LINK}")
        # Публичная анкета (без города и опыта)
        public_text = f"Публичная анкета @{app['username']}:\n\n"
        for q_text, q_key in questions:
            if q_key not in ["user_city", "user_experience"]:
                public_text += f"{q_text} {app[q_key]}\n"
        # Отправка всем админам (можно изменить на общий чат для пользователей)
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, public_text)
        await callback_query.answer("Заявка принята")

    elif data.startswith("reject_"):
        cursor.execute("UPDATE applications SET status='rejected' WHERE user_id=?", (user_id,))
        conn.commit()
        await bot.send_message(user_id, f"К сожалению, {app['user_name']}, ваша заявка отклонена.")
        await callback_query.answer("Заявка отклонена")
__
    elif data.startswith("show_private_"):
        # Показ полной приватной анкеты админам
        private_text = "Приватная анкета:\n\n" + "\n".join([f"{q[0]} {app[q[1]]}" for q in questions])
        await callback_query.message.answer(private_text)
        await callback_query.answer("Приватная анкета показана")

# -----------------------
# Показ публичных анкет пользователям
@dp.callback_query_handler(lambda c: c.data == "show_public")
async def show_public(callback_query: types.CallbackQuery):
    cursor.execute("SELECT * FROM applications WHERE status='accepted'")
    rows = cursor.fetchall()
    if not rows:
        await callback_query.message.answer("Пока нет опубликованных анкет.")
        return
    for row in rows:
        app = dict(zip([column[0] for column in cursor.description], row))
        public_text = f"Публичная анкета @{app['username']}:\n\n"
        for q_text, q_key in questions:
            if q_key not in ["user_city", "user_experience"]:
                public_text += f"{q_text} {app[q_key]}\n"
        await callback_query.message.answer(public_text)
    await callback_query.answer()

# ========================
# Запуск бота
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
