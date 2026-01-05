import os
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = "8514654568:AAGEND_i5FVNLKND88GE1vEfPr0zSEZeDfI"

# ================= DATABASE =================
conn = sqlite3.connect("accounting.db", check_same_thread=False)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    type TEXT
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    account_id INTEGER,
    debit INTEGER,
    credit INTEGER,
    date TEXT
);

CREATE TABLE IF NOT EXISTS pending (
    user_id INTEGER,
    name TEXT,
    source TEXT,
    amount INTEGER
);

CREATE TABLE IF NOT EXISTS setup_state (
    user_id INTEGER PRIMARY KEY,
    step INTEGER
);
""")
conn.commit()

# ================= HELPERS =================
def get_account(user_id, name):
    cursor.execute(
        "SELECT id, type FROM accounts WHERE user_id=? AND LOWER(name)=LOWER(?)",
        (user_id, name)
    )
    return cursor.fetchone()

def create_account(user_id, name, acc_type):
    cursor.execute(
        "INSERT INTO accounts (user_id, name, type) VALUES (?, ?, ?)",
        (user_id, name.capitalize(), acc_type)
    )
    conn.commit()
    return cursor.lastrowid

def post_entry(user_id, debit_acc, credit_acc, amount):
    date = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO journal VALUES (NULL, ?, ?, ?, 0, ?)",
        (user_id, debit_acc, amount, date)
    )
    cursor.execute(
        "INSERT INTO journal VALUES (NULL, ?, ?, 0, ?, ?)",
        (user_id, credit_acc, amount, date)
    )
    conn.commit()

def balance(user_id, name):
    acc = get_account(user_id, name)
    if not acc:
        return 0
    acc_id = acc[0]
    cursor.execute("""
        SELECT COALESCE(SUM(debit-credit),0)
        FROM journal WHERE user_id=? AND account_id=?
    """, (user_id, acc_id))
    return cursor.fetchone()[0]

# ================= START & SETUP =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    for acc in ["Cash", "Bank", "PayPay"]:
        if not get_account(user_id, acc):
            create_account(user_id, acc, "Asset")

    cursor.execute(
        "INSERT OR IGNORE INTO setup_state VALUES (?, 1)",
        (user_id,)
    )
    conn.commit()

    await update.message.reply_text(
        "👋 Welcome!\n\nHow much CASH do you have now?"
    )

async def handle_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    cursor.execute("SELECT step FROM setup_state WHERE user_id=?", (user_id,))
    step = cursor.fetchone()

    if not step or not text.isdigit():
        return

    amount = int(text)
    step = step[0]

    if step == 1:
        post_entry(user_id, get_account(user_id, "Cash")[0], get_account(user_id, "Cash")[0], amount)
        cursor.execute("UPDATE setup_state SET step=2 WHERE user_id=?", (user_id,))
        await update.message.reply_text("🏦 How much BANK balance?")
    elif step == 2:
        post_entry(user_id, get_account(user_id, "Bank")[0], get_account(user_id, "Bank")[0], amount)
        cursor.execute("UPDATE setup_state SET step=3 WHERE user_id=?", (user_id,))
        await update.message.reply_text("📱 How much PayPay balance?")
    elif step == 3:
        post_entry(user_id, get_account(user_id, "PayPay")[0], get_account(user_id, "PayPay")[0], amount)
        cursor.execute("DELETE FROM setup_state WHERE user_id=?", (user_id,))
        await update.message.reply_text("✅ Setup complete! Start typing expenses.")

    conn.commit()

# ================= MAIN INPUT =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip().lower().split()

    if len(text) < 2:
        return

    # WITHDRAWAL
    if "withdraw" in text or "withdrawal" in text:
        source = "bank"
        amount = int(text[-1])
        post_entry(user_id,
                   get_account(user_id, "Cash")[0],
                   get_account(user_id, "Bank")[0],
                   amount)
        await update.message.reply_text("🏦 Withdrawal recorded")
        return

    # PAYPAY CHARGE
    if "charge" in text:
        amount = int(text[-1])
        post_entry(user_id,
                   get_account(user_id, "PayPay")[0],
                   get_account(user_id, "Bank")[0],
                   amount)
        await update.message.reply_text("📱 PayPay charged")
        return

    name = text[0].capitalize()
    source = text[1].capitalize()
    amount = int(text[-1])

    acc = get_account(user_id, name)

    if not acc:
        cursor.execute("INSERT INTO pending VALUES (?, ?, ?, ?)",
                       (user_id, name, source, amount))
        conn.commit()

        keyboard = ReplyKeyboardMarkup(
            [["Expense", "Income"]], one_time_keyboard=True, resize_keyboard=True
        )
        await update.message.reply_text(
            f'❓ Is "{name}" Expense or Income?',
            reply_markup=keyboard
        )
        return

    acc_id, acc_type = acc
    source_id = get_account(user_id, source)[0]

    if acc_type == "Expense":
        post_entry(user_id, acc_id, source_id, amount)
    else:
        post_entry(user_id, source_id, acc_id, amount)

    await update.message.reply_text(f"✅ {name} ¥{amount} saved")

# ================= PENDING RESOLUTION =================
async def resolve_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    choice = update.message.text.lower()

    cursor.execute("SELECT * FROM pending WHERE user_id=?", (user_id,))
    pending = cursor.fetchone()
    if not pending:
        return

    _, name, source, amount = pending
    acc_type = "Expense" if choice == "expense" else "Income"

    acc_id = create_account(user_id, name, acc_type)
    source_id = get_account(user_id, source)[0]

    if acc_type == "Expense":
        post_entry(user_id, acc_id, source_id, amount)
    else:
        post_entry(user_id, source_id, acc_id, amount)

    cursor.execute("DELETE FROM pending WHERE user_id=?", (user_id,))
    conn.commit()

    await update.message.reply_text(f"✅ {name} set as {acc_type}")

# ================= BALANCE =================
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg = (
        f"💵 Cash: ¥{balance(user_id,'Cash')}\n"
        f"🏦 Bank: ¥{balance(user_id,'Bank')}\n"
        f"📱 PayPay: ¥{balance(user_id,'PayPay')}"
    )
    await update.message.reply_text(msg)

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()
app.bot.delete_webhook(drop_pending_updates=True)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("balance", balance_cmd))
app.add_handler(MessageHandler(filters.Regex("^(Expense|Income)$"), resolve_pending))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_setup))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
