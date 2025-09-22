from fastapi import FastAPI
from fastapi.responses import Response
import requests
import datetime
import json
import asyncio
import os

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
TARGET_HOUR = 4  # daily schedule hour
TARGET_MINUTE = 58  # daily schedule minute
LOOP_DURATION_MIN = 10  # loop max duration in minutes
LOOP_INTERVAL_SEC = 1  # interval between attempts in seconds

# Ensure output dir
os.makedirs("runs", exist_ok=True)

# === GLOBAL FLAGS ===
_loop_active = False
_schedule_task = None
_last_result = None  # will store last run summary


# === MAIN FUNCTION ===
def submit():
    """Submit once and return result dict."""
    url = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"
    try:
        res = requests.post(url, data=payload, timeout=30)
        text = res.text.lower()

        # save raw HTML (latest only)
        with open("runs/test.html", "w", encoding="utf-8") as f:
            f.write(res.text.lower())

        if "informasi untuk pasien bpjs<br>" in text:
            return {"status": "success", "message": "✅ Submission recorded"}
        elif (
            "formulir ini tidak menerima jawaban" in text
            or "form is no longer accepting responses" in text
        ):
            return {"status": "closed", "message": "⛔ Form closed"}
        else:
            return {"status": "fail", "message": "❌ Fail to submit, check manually"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# === LOOP FUNCTION (used by manual + scheduled) ===
async def run_submit_loop():
    """Run loop every LOOP_INTERVAL_SEC for up to LOOP_DURATION_MIN."""
    global _loop_active, _last_result
    _loop_active = True

    start = datetime.datetime.now()
    end = start + datetime.timedelta(minutes=LOOP_DURATION_MIN)

    attempts = []
    try:
        while datetime.datetime.now() < end and _loop_active:
            result = await asyncio.get_running_loop().run_in_executor(None, submit)
            result["timestamp"] = datetime.datetime.now().isoformat()
            attempts.append(result)

            # log to console
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {result.get('status').upper()}: {result.get('message')}")

            if result.get("status") == "success":
                break

            await asyncio.sleep(LOOP_INTERVAL_SEC)
    finally:
        _loop_active = False
        if attempts:
            _last_result = attempts[-1]  # save last attempt result

    return attempts


# === ROUTES ===
@app.get("/")
def root():
    return {"message": "Google Form Submitter API is running 🚀"}


@app.get("/submit")
def submit_form():
    result = submit()
    result["timestamp"] = datetime.datetime.now().isoformat()

    global _last_result
    _last_result = result  # update last result for manual submit

    return Response(
        content=json.dumps(result, indent=4, ensure_ascii=False),
        media_type="application/json",
    )


@app.get("/submit_loop")
async def submit_loop():
    """Manual trigger: run loop right now."""
    attempts = await run_submit_loop()
    return Response(
        content=json.dumps(attempts, indent=4, ensure_ascii=False),
        media_type="application/json",
    )


@app.get("/deactivate")
def deactivate_loop():
    """Manually stop the loop early."""
    global _loop_active
    _loop_active = False
    return {"status": "deactivated"}


@app.get("/status")
def status_loop():
    """Check if loop is currently active + last run result."""
    return {
        "running": _loop_active,
        "last_result": _last_result,
    }


# === SCHEDULER (auto-run at TARGET_HOUR:TARGET_MINUTE) ===
async def scheduled_runner():
    """Wait until target time each day and run the loop."""
    while True:
        now = datetime.datetime.now()
        run_time = now.replace(
            hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0
        )

        # if already past target time today, schedule for tomorrow
        if run_time <= now:
            run_time += datetime.timedelta(days=1)

        wait_seconds = (run_time - now).total_seconds()
        print(f"⏳ Waiting {wait_seconds/60:.1f} minutes until {run_time}")
        await asyncio.sleep(wait_seconds)

        # run the loop
        print(
            f"⏰ Time reached! Running submit loop for {LOOP_DURATION_MIN} minutes..."
        )
        await run_submit_loop()

        print("✅ Auto-loop finished. Will wait until tomorrow...")


@app.on_event("startup")
async def start_scheduler():
    """Start daily scheduler when FastAPI boots."""
    global _schedule_task
    _schedule_task = asyncio.create_task(scheduled_runner())
