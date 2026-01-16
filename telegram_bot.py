from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import subprocess
import os
import time

BOT_TOKEN = "8246411617:AAGSc6Yy-sR5Aaa4AmepeDNrePlQV9y1hg4"
LOG_DIR = "/home/pi/logs"

def cron_jobs():
    jobs = {}
    crontab = subprocess.getoutput("crontab -l")
    for line in crontab.splitlines():
        if line.strip() and not line.startswith("#"):
            parts = line.split()
            cmd = " ".join(parts[5:])
            for p in cmd.split():
                if p.endswith(".log"):
                    job = os.path.basename(p).replace(".log", "")
                    jobs[job] = cmd
    return jobs

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📊 Job Status:\n"
    for f in os.listdir(LOG_DIR):
        if f.endswith(".log"):
            path = f"{LOG_DIR}/{f}"
            t = time.ctime(os.path.getmtime(path))
            msg += f"\n🔹 {f.replace('.log','')}\n🕒 Last log update: {t}\n"
    await update.message.reply_text(msg)

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /log jobname [lines]")
        return

    job = context.args[0]
    lines = 10  # default
    if len(context.args) > 1:
        try:
            lines = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Lines must be an integer")
            return

    log_file = f"{LOG_DIR}/{job}.log"
    if not os.path.exists(log_file):
        await update.message.reply_text("❌ Log not found")
        return

    output = subprocess.getoutput(f"tail -n {lines} {log_file}")
    await update.message.reply_text(f"📄 {job} log (last {lines} lines):\n{output}")

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /run jobname")
        return

    job = context.args[0]
    jobs = cron_jobs()

    if job not in jobs:
        await update.message.reply_text("❌ Job not found in crontab")
        return

    await update.message.reply_text(f"▶ Running {job}...")
    subprocess.Popen(jobs[job], shell=True)
    await update.message.reply_text(f"✅ {job} started")

async def cron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 6:
        await update.message.reply_text(
            "Usage:\n/cron <job> <min> <hour> <day> <month> <weekday>"
        )
        return

    job, m, h, d, mo, w = context.args
    jobs = cron_jobs()

    if job not in jobs:
        await update.message.reply_text("❌ Job not found")
        return

    cmd = jobs[job]
    new_line = f"{m} {h} {d} {mo} {w} {cmd}"

    subprocess.run(
        f"(crontab -l | grep -v '{cmd}'; echo \"{new_line}\") | crontab -",
        shell=True
    )

    await update.message.reply_text(f"⏱ Schedule updated for {job}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("log", log))
app.add_handler(CommandHandler("run", run))
app.add_handler(CommandHandler("cron", cron))

app.run_polling()
