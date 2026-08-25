import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from database import get_connection, init_database


# =========================
# CONFIG
# =========================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

UZBEKISTAN_TZ = ZoneInfo("Asia/Tashkent")

GOAL, TIME = range(2)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        ["🎯 Maqsad qo‘shish"],
        ["📋 Bugungi maqsadlar", "📊 Statistika"],
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(
        "👋 Salom!\n\n"
        "Men sening Daily Assistant botingman. 🤖\n\n"
        "Bugungi kuningni birga rejalashtiramiz!",
        reply_markup=reply_markup
    )


# =========================
# ADD GOAL
# =========================

async def add_goal_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🎯 Bugungi maqsadingni yoz:"
    )

    return GOAL


async def receive_goal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data["goal"] = update.message.text

    await update.message.reply_text(
        "⏰ Qaysi vaqtda eslatay?\n\n"
        "Masalan: 18:00"
    )

    return TIME


async def receive_time(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    time_text = update.message.text
    goal = context.user_data["goal"]

    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:

        await update.message.reply_text(
            "❌ Vaqt noto‘g‘ri.\n\n"
            "Masalan: 18:00"
        )

        return TIME

    now = datetime.now(UZBEKISTAN_TZ)

    today = now.strftime("%Y-%m-%d")

    user_id = update.effective_user.id

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO goals
        (user_id, title, goal_date, goal_time)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            goal,
            today,
            time_text
        )
    )

    connection.commit()

    goal_id = cursor.lastrowid

    connection.close()

    await update.message.reply_text(
        f"✅ Maqsad saqlandi!\n\n"
        f"🎯 {goal}\n"
        f"⏰ {time_text}"
    )

    schedule_goal_reminder(
        context.application,
        user_id,
        goal_id,
        goal,
        today,
        time_text
    )

    context.user_data.clear()

    return ConversationHandler.END


# =========================
# SCHEDULE REMINDER
# =========================

def schedule_goal_reminder(
    application,
    user_id,
    goal_id,
    goal,
    goal_date,
    goal_time
):

    now = datetime.now(UZBEKISTAN_TZ)

    year, month, day = map(
        int,
        goal_date.split("-")
    )

    hour, minute = map(
        int,
        goal_time.split(":")
    )

    reminder_time = datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=UZBEKISTAN_TZ
    )

    if reminder_time <= now:
        return

    delay = (
        reminder_time - now
    ).total_seconds()

    application.job_queue.run_once(
        send_reminder,
        delay,
        data={
            "user_id": user_id,
            "goal_id": goal_id,
            "goal": goal,
        },
        name=f"goal_{goal_id}"
    )


# =========================
# RESTORE REMINDERS
# =========================

def restore_today_reminders(application):

    now = datetime.now(UZBEKISTAN_TZ)

    today = now.strftime("%Y-%m-%d")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, user_id, title, goal_date, goal_time
        FROM goals
        WHERE goal_date = ?
        AND completed = 0
        AND goal_time IS NOT NULL
        """,
        (today,)
    )

    goals = cursor.fetchall()

    connection.close()

    for goal_id, user_id, title, goal_date, goal_time in goals:

        schedule_goal_reminder(
            application,
            user_id,
            goal_id,
            title,
            goal_date,
            goal_time
        )


# =========================
# SEND REMINDER
# =========================

async def send_reminder(
    context: ContextTypes.DEFAULT_TYPE
):

    data = context.job.data

    user_id = data["user_id"]
    goal_id = data["goal_id"]
    goal = data["goal"]

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Bajarildi",
                callback_data=f"done:{goal_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "⏰ 10 daqiqadan keyin",
                callback_data=f"snooze:{goal_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Bugun bajarmayman",
                callback_data=f"skip:{goal_id}"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "🔔 Eslatma!\n\n"
            f"🎯 {goal}\n\n"
            "Vazifani bajardingmi?"
        ),
        reply_markup=reply_markup
    )


# =========================
# REMINDER BUTTONS
# =========================

async def reminder_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    action, goal_id = query.data.split(":")

    goal_id = int(goal_id)

    connection = get_connection()
    cursor = connection.cursor()

    if action == "done":

        cursor.execute(
            """
            UPDATE goals
            SET completed = 1
            WHERE id = ?
            """,
            (goal_id,)
        )

        connection.commit()

        connection.close()

        await query.edit_message_text(
            "✅ Ajoyib!\n\n"
            "Maqsad bajarildi. 🔥"
        )

    elif action == "skip":

        connection.close()

        await query.edit_message_text(
            "❌ Mayli.\n\n"
            "Bu maqsad bugun bajarilmadi."
        )

    elif action == "snooze":

        cursor.execute(
            """
            SELECT user_id, title
            FROM goals
            WHERE id = ?
            """,
            (goal_id,)
        )

        result = cursor.fetchone()

        connection.close()

        if result:

            user_id, goal = result

            context.job_queue.run_once(
                send_reminder,
                600,
                data={
                    "user_id": user_id,
                    "goal_id": goal_id,
                    "goal": goal,
                },
                name=f"snooze_{goal_id}"
            )

            await query.edit_message_text(
                "⏰ Mayli!\n\n"
                "10 daqiqadan keyin yana eslataman."
            )


# =========================
# SHOW GOALS
# =========================

async def show_goals(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    now = datetime.now(UZBEKISTAN_TZ)

    today = now.strftime("%Y-%m-%d")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, title, goal_time, completed
        FROM goals
        WHERE user_id = ?
        AND goal_date = ?
        ORDER BY goal_time
        """,
        (
            user_id,
            today
        )
    )

    goals = cursor.fetchall()

    connection.close()

    if not goals:

        await update.message.reply_text(
            "📋 Bugun uchun hali maqsadlaringiz yo‘q."
        )

        return

    message = "📋 Bugungi maqsadlaring:\n\n"

    for number, (_, title, goal_time, completed) in enumerate(
        goals,
        start=1
    ):

        status = "✅" if completed else "⬜"

        message += (
            f"{number}. {status} {title}\n"
            f"   ⏰ {goal_time or 'Vaqt belgilanmagan'}\n\n"
        )

    await update.message.reply_text(
        message
    )


# =========================
# STATISTICS
# =========================

async def show_statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*),
            SUM(completed)
        FROM goals
        WHERE user_id = ?
        """,
        (user_id,)
    )

    total, completed = cursor.fetchone()

    connection.close()

    total = total or 0
    completed = completed or 0

    if total == 0:

        await update.message.reply_text(
            "📊 Hali statistika uchun ma'lumot yetarli emas."
        )

        return

    percentage = round(
        completed / total * 100
    )

    await update.message.reply_text(
        "📊 Sening statistikang:\n\n"
        f"🎯 Jami maqsadlar: {total}\n"
        f"✅ Bajarilgan: {completed}\n"
        f"📈 Bajarilish: {percentage}%"
    )


# =========================
# DAILY CHECK-IN
# =========================

async def daily_check_in(
    context: ContextTypes.DEFAULT_TYPE
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT DISTINCT user_id
        FROM goals
        """
    )

    users = cursor.fetchall()

    connection.close()

    for (user_id,) in users:

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🌅 Xayrli tong!\n\n"
                    "Bugun qanday maqsadlaring bor?\n\n"
                    "🎯 Maqsad qo‘shish tugmasidan "
                    "foydalanishing mumkin."
                )
            )

        except Exception as error:

            print(
                f"Check-in yuborishda xato: {error}"
            )


# =========================
# BUTTON HANDLER
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text

    if text == "📋 Bugungi maqsadlar":

        await show_goals(
            update,
            context
        )

    elif text == "📊 Statistika":

        await show_statistics(
            update,
            context
        )


# =========================
# CANCEL
# =========================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ Maqsad qo‘shish bekor qilindi."
    )

    return ConversationHandler.END


# =========================
# MAIN
# =========================

def main():

    init_database()

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # Maqsad qo‘shish
    goal_conversation = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex(
                    "^🎯 Maqsad qo‘shish$"
                ),
                add_goal_start
            )
        ],

        states={

            GOAL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_goal
                )
            ],

            TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_time
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel
            )
        ]
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        goal_conversation
    )

    application.add_handler(
        CallbackQueryHandler(
            reminder_button
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            button_handler
        )
    )

    # Bugungi reminderlarni tiklash
    restore_today_reminders(
        application
    )

    # Har kuni 07:00 check-in
    application.job_queue.run_daily(
        daily_check_in,
        time=datetime(
            2026,
            1,
            1,
            7,
            0,
            tzinfo=UZBEKISTAN_TZ
        ).timetz()
    )

    print("🤖 Bot ishga tushdi...")
    print("⏰ Reminder tizimi faol.")
    print("🌅 Daily Check-in: 07:00")

    application.run_polling()


if __name__ == "__main__":
    main()