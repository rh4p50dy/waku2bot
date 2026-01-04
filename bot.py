from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
import sqlite3
from datetime import datetime
import os

TOKEN = os.getenv("BOT_TOKEN")

conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT,
    amount INTEGER,
    date TEXT,
    month TEXT,
    year TEXT
)
""")
conn.commit()

def save_expense(user_id, title, amount):
    now = datetime.now()
    cursor.execute("""
        INSERT INTO expenses (user_id, title, amount, date, month, year)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        title,
        amount,
        now.strftime("%Y-%m-%d"),
        now.strftime("%Y-%m"),
        now.strftime("%Y")
    ))
    conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💸 Expense Tracker Bot\nSend: Coffee 195\nCommands: /today /month /advice"
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id=? AND date=?", (uid, today))
    total = cursor.fetchone()[0] or 0
    await update.message.reply_text(f"📅 Today: ¥{total}")

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    month = datetime.now().strftime("%Y-%m")
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id=? AND month=?", (uid, month))
    total = cursor.fetchone()[0] or 0
    await update.message.reply_text(f"📊 Month: ¥{total}")

async def advice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    month = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT title, SUM(amount) FROM expenses
        WHERE user_id=? AND month=?
        GROUP BY title ORDER BY SUM(amount) DESC LIMIT 1
    """, (uid, month))
    top = cursor.fetchone()
    if top:
        await update.message.reply_text(
            f"💡 Most spending: {top[0]} (¥{top[1]})\nTry reducing it."
        )
    else:
        await update.message.reply_text("No data yet.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or not parts[-1].isdigit():
        await update.message.reply_text("Format: Coffee 195")
        return

    amount = int(parts[-1])
    title = " ".join(parts[:-1])
    save_expense(update.message.from_user.id, title, amount)
    await update.message.reply_text(f"✅ Saved {title}: ¥{amount}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("today", today))
app.add_handler(CommandHandler("month", month))
app.add_handler(CommandHandler("advice", advice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
