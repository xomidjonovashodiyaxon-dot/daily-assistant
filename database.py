import sqlite3

DATABASE = "daily_assistant.db"


def get_connection():
    return sqlite3.connect(DATABASE)


def init_database():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            goal_date TEXT NOT NULL,
            goal_time TEXT,
            completed INTEGER DEFAULT 0,
            reminder_sent INTEGER DEFAULT 0
        )
    """)

    connection.commit()
    connection.close()