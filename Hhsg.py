from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import subprocess
import os
import time

BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN"
LOG_DIR = "/home/pi/logs"
SCRIPTS_DIR = "/home/pi/scripts"

# ----------------------
# Helper functions
# ----------------------
def get_jobs():
    return [f.replace(".log", "") for f in os.listdir(LOG_DIR) if f.endswith(".log")]

def get_job_command(job):
    crontab = subprocess.getoutput("crontab -l")
    for line in crontab.splitlines():
        if job in line:
            return " ".join(line.split()[5:])
    return None

# ----------------------
# Main menu
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("▶ Run Job", callback_data="run_menu")],
        [InlineKeyboardButton("📄 View Logs", callback_data="log_menu")],
        [InlineKeyboardButton("⏱ Update Schedule", callback_data="cron_menu")],
    ]
    await update.message.reply_text("📌 Bot Menu:", reply_markup=InlineKeyboardMarkup(keyboard))

# ----------------------
# Button handler
# ----------------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # -------- Status --------
    if data == "status":
        msg = "📊 Job Status:\n"
        for f in os.listdir(LOG_DIR):
            if f.endswith(".log"):
                path = f"{LOG_DIR}/{f}"
                t = os.path.getmtime(path)
                msg += f"\n🔹 {f.replace('.log','')}\n🕒 Last log update: {time.ctime(t)}\n"
        await query.edit_message_text(msg)
        return

    # -------- Run Menu --------
    if data == "run_menu":
        jobs = get_jobs()
        keyboard = [[InlineKeyboardButton(job, callback_data=f"run:{job}")] for job in jobs]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="start")])
        await query.edit_message_text("▶ Select job to run:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # -------- Log Menu --------
    if data == "log_menu":
        jobs = get_jobs()
        keyboard = [[InlineKeyboardButton(job, callback_data=f"log:{job}:10")] for job in jobs]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="start")])
        await query.edit_message_text("📄 Select job to view last 10 lines of logs:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # -------- Cron Menu --------
    if data == "cron_menu":
        jobs = get_jobs()
        keyboard = [[InlineKeyboardButton(job, callback_data=f"cron:{job}") ] for job in jobs]
        keyboard.append([InlineKeyboardButton("⬅ Back", callback_data="start")])
        await query.edit_message_text("⏱ Select job to update schedule:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # -------- Run Job Action --------
    if data.startswith("run:"):
        job = data.split(":")[1]
        cmd = get_job_command(job)
        if cmd:
            subprocess.Popen(cmd, shell=True)
            await query.edit_message_text(f"▶ {job} started!")
        else:
            await query.edit_message_text(f"❌ Job {job} not found in crontab")
        return

    # -------- Log Action --------
    if data.startswith("log:"):
        _, job, lines = data.split(":")
        log_file = f"{LOG_DIR}/{job}.log"
        if os.path.exists(log_file):
            output = subprocess.getoutput(f"tail -n {lines} {log_file}")
            await query.edit_message_text(f"📄 {job} log (last {lines} lines):\n{output}")
        else:
            await query.edit_message_text(f"❌ Log {job} not found")
        return

    # -------- Cron Edit --------
    if data.startswith("cron:"):
        job = data.split(":")[1]
        cmd = get_job_command(job)
        if not cmd:
            await query.edit_message_text(f"❌ Job {job} not found in crontab")
            return

        # Show editable fields
        keyboard = [
            [InlineKeyboardButton("Set Minute", callback_data=f"cron_set:{job}:min")],
            [InlineKeyboardButton("Set Hour", callback_data=f"cron_set:{job}:hour")],
            [InlineKeyboardButton("Set Day", callback_data=f"cron_set:{job}:day")],
            [InlineKeyboardButton("Set Month", callback_data=f"cron_set:{job}:month")],
            [InlineKeyboardButton("Set Weekday", callback_data=f"cron_set:{job}:weekday")],
            [InlineKeyboardButton("⬅ Back", callback_data="start")]
        ]
        await query.edit_message_text(f"⏱ Update schedule for {job} (manual typing required for now):", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # -------- Back Button --------
    if data == "start":
        await start(update, context)

# ----------------------
# Main
# ----------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.run_polling()
