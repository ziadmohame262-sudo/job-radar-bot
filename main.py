import asyncio
import json
import os
import threading
import time
from google import genai
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# المفاتيح
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6IhiL0GN6ZNgAM1uGSVLA0DKk5r5cGRsc04TMOxHYK6lQ")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8950430378:AAHur1xNJS0T5C1RpyIpvglfLoSFonJub3M")

client = genai.Client(api_key=GEMINI_API_KEY)
USERS_FILE = "users.json"
HISTORY_FILE = "sent_jobs.txt"

# إدارة الملفات
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_user(chat_id, user_data):
    users = load_users()
    users[str(chat_id)] = user_data
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

def get_sent_jobs():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f.readlines())

def mark_job_as_sent(user_id, job_link):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id}|{job_link}\n")

# أوامر البوت التفاعلي
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 Welcome to AI Job Radar!\n\n"
        "Reply with your target role and skills to start receiving matched jobs.\n"
        "Example: 'Python Developer, AI, ML, Junior'"
    )
    await update.message.reply_text(msg)

async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.effective_user.username or update.effective_user.first_name
    skills = update.message.text.strip()
    save_user(chat_id, {"name": name, "skills": skills})
    await update.message.reply_text(f"✅ Saved! Searching opportunities for:\n{skills}")

# فحص الوظائف بالذكاء الاصطناعي
def evaluate_job(skills, title, desc):
    prompt = f"Candidate: {skills}\nJob Title: {title}\nDetails: {desc[:300]}\nMatch? Answer YES or NO and 1 short reason."
    try:
        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
        return res.text
    except Exception:
        return "Match: NO"

def send_alert(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"Error sending alert: {e}")

def fetch_jobs():
    try:
        res = requests.get("https://remotive.com/api/remote-jobs?limit=5", timeout=10)
        return res.json().get("jobs", [])[:5]
    except Exception:
        return []

# تشغيل الفحص في الخلفية كل 30 دقيقة
def job_radar_worker():
    while True:
        try:
            users = load_users()
            sent_records = get_sent_jobs()
            jobs = fetch_jobs()

            for u_id, profile in users.items():
                for job in jobs:
                    link = job.get("url")
                    key = f"{u_id}|{link}"
                    if key in sent_records:
                        continue

                    title = job.get("title")
                    desc = job.get("description", "")
                    decision = evaluate_job(profile.get("skills", ""), title, desc)

                    if "YES" in decision.upper():
                        alert_msg = f"🎯 New Matched Job!\n\n📌 Role: {title}\n🏢 Company: {job.get('company_name')}\n🔗 Link: {link}\n\n🤖 Note: {decision.strip()}"
                        send_alert(u_id, alert_msg)
                        mark_job_as_sent(u_id, link)
                        sent_records.add(key)
                    time.sleep(8)
        except Exception as e:
            print(f"Worker cycle error: {e}")

        # انتظار 30 دقيقة قبل الفحص التالي
        time.sleep(1800)

if __name__ == "__main__":
    # تشغيل محرك الفحص في Thread مستقل بالخلفية
    t = threading.Thread(target=job_radar_worker, daemon=True)
    t.start()

    # تشغيل استقبال رسائل البوت
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile))
    print("[+] System running 24/7...")
    app.run_polling()