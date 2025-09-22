from fastapi import FastAPI
import requests
import datetime

app = FastAPI()

# === CONFIG SECTION ===
FORM_ID = "1FAIpQLSdnRed5lP88j-_McVlF-IUmCFu1w-MFFeqU57SDVCXayNcEHg"

payload = {
    "entry.111111111": "081398804090",  # No HP
    "entry.222222222": "0001256122888",  # No BPJS
    "entry.333333333": "mariyani.lie1971@gmail.com",  # Email
    "entry.444444444": "YULIANA",  # Nama
    "entry.555555555": "Radiasi Kartu Hijau",  # Warna Kartu
}


# === MAIN FUNCTION ===
def submit():
    url = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"
    try:
        res = requests.post(url, data=payload)
        text = res.text.lower()

        if "terima kasih" in text or "your response has been recorded" in text:
            return {"status": "success", "message": "✅ Submission recorded"}
        elif (
            "formulir ini tidak menerima jawaban" in text
            or "form is no longer accepting responses" in text
        ):
            return {
                "status": "closed",
                "message": "⛔ Form closed, submission not accepted",
            }
        elif "entry." in text:
            return {
                "status": "warning",
                "message": "⚠️ Likely wrong field IDs (entry.xxxxx)",
            }
        else:
            return {
                "status": "unknown",
                "message": "❓ Unknown response, check manually",
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# === ROUTES ===
@app.get("/")
def root():
    return {"message": "Google Form Submitter API is running 🚀"}


@app.get("/submit")
def submit_form():
    result = submit()
    result["timestamp"] = datetime.datetime.now().isoformat()
    return result
