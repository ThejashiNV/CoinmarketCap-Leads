from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import pandas as pd
import subprocess
import os
import time
import json


app = FastAPI()

live_logs = []


# -------------------------------
# CORS
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------
# Home
# -------------------------------
@app.get("/")
def home():

    return {
        "message": "Crypto Leads API Running"
    }


# -------------------------------
# Start Extraction
# -------------------------------
@app.post("/start-extraction")
def start_extraction():

    try:

        live_logs.clear()

        process = subprocess.Popen(
            ["venv/Scripts/python.exe", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in process.stdout:

            clean_line = line.strip()

            print(clean_line)

            if clean_line:

                live_logs.append({
                    "message": clean_line
                })

        process.wait()

        return {
            "status": "success",
            "message": "Extraction completed"
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# -------------------------------
# Live Logs API
# -------------------------------
@app.get("/live-logs")
def stream_logs():

    def event_stream():

        last_index = 0

        while True:

            if last_index < len(live_logs):

                data = live_logs[last_index]

                yield (
                    f"data: "
                    f"{json.dumps(data)}\n\n"
                )

                last_index += 1

            time.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )


# -------------------------------
# Leads API
# -------------------------------
@app.get("/leads")
def get_leads():

    file_path = "output/final_leads.csv"

    if not os.path.exists(file_path):

        return []

    df = pd.read_csv(file_path)

    return df.fillna(
        ""
    ).to_dict(
        orient="records"
    )