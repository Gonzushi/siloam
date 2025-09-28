from fastapi import FastAPI
from fastapi.responses import Response
import requests
import datetime
import json
import asyncio
import os
import pytz

app = FastAPI()

# === CONFIG SECTION ===
FORM_ID = "1FAIpQLSdnRed5lP88j-_McVlF-IUmCFu1w-MFFeqU57SDVCXayNcEHg"

payload = {
    "entry.508561614": "0001256122888",  # No BPJS
    "entry.1030180462": "mariyani.lie1971@gmail.com",  # Email
    "entry.793094576": "YULIANA",  # Nama
    "entry.1741489021": "081398804090",  # No HP
    "entry.1202237695": "Radiasi Kartu Hijau",  # Warna Kartu
}

# === LOOP SETTINGS ===
TARGET_HOUR = 4  # daily schedule hour (WIB)
TARGET_MINUTE = 55
TARGET_SECOND = 0
LOOP_DURATION_MIN = 10
LOOP_INTERVAL_SEC = 1

# Ensure output dir
os.makedirs("runs", exist_ok=True)

# === GLOBAL FLAGS ===
_loop_active = False
_schedule_task = None
_last_result = None

# === TIMEZONE (WIB) ===
WIB = pytz.timezone("Asia/Jakarta")


# === MAIN FUNCTION ===
def submit():
    url = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"
    try:
        res = requests.post(url, data=payload, timeout=30)
        text = res.text.lower()

        with open("runs/test.html", "w", encoding="utf-8") as f:
            f.write(res.text.lower())

        if "informasi untuk pasien bpjs<br>" in text:
            return {"status": "success", "message": "✅ Submission recorded"}
        elif "hanya dapat diakses pada jam 05.00-07.00" in text:
            return {"status": "closed", "message": "⛔ Form closed"}
        else:
            return {"status": "fail", "message": "❌ Fail to submit, check manually"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# === LOOP FUNCTION ===
async def run_submit_loop():
    global _loop_active, _last_result
    _loop_active = True

    start = datetime.datetime.now(WIB)
    end = start + datetime.timedelta(minutes=LOOP_DURATION_MIN)

    attempts = []
    try:
        while datetime.datetime.now(WIB) < end and _loop_active:
            result = await asyncio.get_running_loop().run_in_executor(None, submit)
            result["timestamp"] = datetime.datetime.now(WIB).isoformat()
            attempts.append(result)

            ts = datetime.datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts} WIB] {result.get('status').upper()}: {result.get('message')}")

            if result.get("status") == "success":
                break

            await asyncio.sleep(LOOP_INTERVAL_SEC)
    finally:
        _loop_active = False
        if attempts:
            _last_result = attempts[-1]

    return attempts


# === ROUTES ===
@app.get("/")
def root():
    now = datetime.datetime.now(WIB)
    run_time = now.replace(
        hour=TARGET_HOUR, minute=TARGET_MINUTE, second=TARGET_SECOND, microsecond=0
    )

    # if already past today's target, move to tomorrow
    if run_time <= now:
        run_time += datetime.timedelta(days=1)

    # skip weekends (Sat=5, Sun=6)
    while run_time.weekday() >= 5:
        run_time += datetime.timedelta(days=1)

    diff_seconds = (run_time - now).total_seconds()
    minutes_away = diff_seconds / 60
    hours, minutes = divmod(int(minutes_away), 60)

    result = {
        "running": _loop_active,
        "last_result": _last_result,
        "server_time_wib": now.isoformat(),
        "next_schedule": {
            "next_schedule_time_wib": run_time.isoformat(),
            "minutes_away": round(minutes_away, 2),
            "time_left": f"{hours}h {minutes}m",
            "weekday": run_time.strftime("%A"),
        },
    }

    return Response(
        content=json.dumps(result, indent=4, ensure_ascii=False),
        media_type="application/json",
    )


@app.get("/submit")
def submit_form():
    result = submit()
    result["timestamp"] = datetime.datetime.now(WIB).isoformat()

    global _last_result
    _last_result = result
    return Response(
        content=json.dumps(result, indent=4, ensure_ascii=False),
        media_type="application/json",
    )


@app.get("/submit_loop")
async def submit_loop():
    attempts = await run_submit_loop()
    return Response(
        content=json.dumps(attempts, indent=4, ensure_ascii=False),
        media_type="application/json",
    )


@app.get("/deactivate")
def deactivate_loop():
    global _loop_active
    _loop_active = False
    result = {
        "status": "deactivated",
        "timestamp": datetime.datetime.now(WIB).isoformat(),
    }
    return Response(
        content=json.dumps(result, indent=4, ensure_ascii=False),
        media_type="application/json",
    )


# === SCHEDULER ===
async def scheduled_runner():
    while True:
        now = datetime.datetime.now(WIB)
        run_time = now.replace(
            hour=TARGET_HOUR, minute=TARGET_MINUTE, second=TARGET_SECOND, microsecond=0
        )

        # if already past target time today, schedule for tomorrow
        if run_time <= now:
            run_time += datetime.timedelta(days=1)

        wait_seconds = (run_time - now).total_seconds()
        print(f"⏳ Waiting {wait_seconds/60:.1f} minutes until {run_time} WIB")
        await asyncio.sleep(wait_seconds)

        # Only run if it's Monday–Friday
        weekday = run_time.weekday()  # 0=Mon ... 6=Sun
        if weekday < 5:
            print(
                f"⏰ Time reached {run_time} WIB (Weekday {weekday})! Running submit loop..."
            )
            await run_submit_loop()
            print("✅ Auto-loop finished. Will wait until tomorrow...")
        else:
            print(f"🚫 {run_time.strftime('%A')} (Weekend). Skipping loop.")


@app.on_event("startup")
async def start_scheduler():
    global _schedule_task
    _schedule_task = asyncio.create_task(scheduled_runner())
