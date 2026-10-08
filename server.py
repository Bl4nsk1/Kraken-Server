from flask import Flask, render_template, request, Response, jsonify, abort
from werkzeug.utils import secure_filename
import json
import os
import queue
import re
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timezone

app = Flask(__name__)

UPLOAD_FOLDER = ""
CAP2HASH_SCRIPT = ""
HASHCATER_SCRIPT = ""
HASHCAT_PATH = ""
DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kraken_data")
JOBS_FOLDER = os.path.join(DATA_FOLDER, "jobs")
DATABASE_PATH = os.path.join(DATA_FOLDER, "jobs.sqlite3")
ALLOWED_EXTENSIONS = {"pcap", "cap", "pcapng"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(JOBS_FOLDER, exist_ok=True)

jobs = {}
jobs_lock = threading.RLock()

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def job_log_path(job_id):
    return os.path.join(JOBS_FOLDER, f"{job_id}.log")

def db_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database():
    with db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                files_json TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                returncode INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)"
        )

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def append_log(job_id, message):
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    with open(job_log_path(job_id), "a", encoding="utf-8", errors="replace") as log_file:
        log_file.write(line + "\n")
    print(f"[JOB {job_id}] {message}", flush=True)

def create_job(filenames):
    job_id = str(uuid.uuid4())
    created_at = utc_now()
    job = {
        "id": job_id,
        "files": filenames,
        "status": "queued",
        "stage": "upload",
        "done": False,
        "returncode": None,
        "created_at": created_at,
        "updated_at": created_at,
        "finished_at": None,
        "queue": queue.Queue()
    }

    with jobs_lock:
        jobs[job_id] = job

    with db_connection() as connection:
        connection.execute("""
            INSERT INTO jobs
            (id, files_json, status, stage, done, returncode, created_at, updated_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, json.dumps(filenames, ensure_ascii=False), "queued", "upload",
            0, None, created_at, created_at, None
        ))

    append_log(job_id, f"[SYSTEM] Job created. Files: {', '.join(filenames)}")
    return job_id

def update_job_db(job):
    with db_connection() as connection:
        connection.execute("""
            UPDATE jobs
            SET status = ?, stage = ?, done = ?, returncode = ?,
                updated_at = ?, finished_at = ?
            WHERE id = ?
        """, (
            job["status"], job["stage"], int(job["done"]), job["returncode"],
            job["updated_at"], job["finished_at"], job["id"]
        ))

def send_event(job_id, stage, status, message):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["stage"] = stage
        job["status"] = status
        job["updated_at"] = utc_now()
        update_job_db(job)

    append_log(job_id, message)
    job["queue"].put({
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": utc_now()
    })

def finish_job(job_id, status, returncode):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["status"] = status
        job["returncode"] = returncode
        job["done"] = True
        job["updated_at"] = utc_now()
        job["finished_at"] = utc_now()
        update_job_db(job)
        stage = job["stage"]

    message = f"[SYSTEM] Job finished: status={status}, returncode={returncode}."
    append_log(job_id, message)
    job["queue"].put({
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": utc_now()
    })

def strip_ansi(value):
    return re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", value)

def run_process(job_id, stage, command):
    send_event(job_id, stage, "running", f"[{stage.upper()}] Starting: {' '.join(command)}")

    try:
        process = subprocess.Popen(
            ["stdbuf", "-oL", "-eL"] + command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
    except Exception as error:
        send_event(job_id, stage, "failed", f"[{stage.upper()}] Failed to start: {error}")
        return False, 1

    if process.stdout:
        for raw_line in iter(process.stdout.readline, ""):
            # Hashcat uses carriage returns for in-place status updates.
            for line in re.split(r"[\r\n]+", raw_line):
                line = strip_ansi(line).strip()
                if line:
                    send_event(job_id, stage, "running", f"[{stage.upper()}] {line}")
        process.stdout.close()

    returncode = process.wait()
    if returncode != 0:
        send_event(job_id, stage, "failed",
                   f"[{stage.upper()}] Process exited with code {returncode}.")
        return False, returncode

    send_event(job_id, stage, "completed", f"[{stage.upper()}] Completed successfully.")
    return True, 0

def run_cap2hash(job_id):
    # This preserves the current shared-folder workflow. For strict per-job isolation,
    # pass a job-specific directory to Cap2Hash and HashCater.
    return run_process(job_id, "cap2hash", ["bash", CAP2HASH_SCRIPT, UPLOAD_FOLDER])

def run_hashcater(job_id):
    command = [
        "bash", HASHCATER_SCRIPT,
        "-H", UPLOAD_FOLDER,
        "-C", HASHCAT_PATH,
        "-A", "bruteforce",
        "-m", "22000",
        "-v"
    ]
    return run_process(job_id, "hashcat", command)

def process_job(job_id):
    append_log(job_id, "[SYSTEM] Processing started.")

    cap2hash_success, cap2hash_code = run_cap2hash(job_id)
    if not cap2hash_success:
        finish_job(job_id, "failed", cap2hash_code)
        return

    hash_files = [
        filename for filename in os.listdir(UPLOAD_FOLDER)
        if filename.lower().endswith(".hc22000")
    ]
    if not hash_files:
        send_event(job_id, "hashcat", "failed", "[HASHCAT] No .hc22000 files found.")
        finish_job(job_id, "failed", 1)
        return

    send_event(job_id, "hashcat", "running",
               f"[HASHCAT] Found {len(hash_files)} .hc22000 file(s).")
    hashcat_success, hashcat_code = run_hashcater(job_id)

    if not hashcat_success:
        finish_job(job_id, "failed", hashcat_code)
        return

    finish_job(job_id, "completed", 0)
    append_log(job_id, "[SYSTEM] Processing completed.")


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "GET":
        return render_template("index.html")

    files = request.files.getlist("file")
    if not files:
        return "No file uploaded", 400

    saved_files = []
    for uploaded_file in files:
        if not uploaded_file or not uploaded_file.filename:
            continue
        if not allowed_file(uploaded_file.filename):
            return f"Invalid file: {uploaded_file.filename}", 400

        filename = secure_filename(uploaded_file.filename)
        if not filename:
            return "Invalid filename", 400

        filepath = os.path.join(UPLOAD_FOLDER, filename)
        uploaded_file.save(filepath)
        saved_files.append(filename)

    if not saved_files:
        return "No valid files uploaded", 400

    job_id = create_job(saved_files)
    worker = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    worker.start()
    return render_template("sucess.html", job_id=job_id, filenames=saved_files)


@app.route("/history")
def history():
    with db_connection() as connection:
        rows = connection.execute("""
            SELECT id, files_json, status, stage, done, returncode,
                   created_at, updated_at, finished_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT 500
        """).fetchall()

    history_jobs = []
    for row in rows:
        item = dict(row)
        item["files"] = json.loads(item.pop("files_json"))
        item["done"] = bool(item["done"])
        history_jobs.append(item)

    return render_template("history.html", jobs=history_jobs)


@app.route("/jobs/<job_id>")
def job_detail(job_id):
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()

    if row is None:
        abort(404)

    item = dict(row)
    item["files"] = json.loads(item.pop("files_json"))
    item["done"] = bool(item["done"])

    try:
        with open(job_log_path(job_id), "r", encoding="utf-8", errors="replace") as log_file:
            log_text = log_file.read()
    except FileNotFoundError:
        log_text = "No log file was saved for this job."

    return render_template("job_detail.html", job=item, log_text=log_text)


@app.route("/api/jobs")
def api_jobs():
    with db_connection() as connection:
        rows = connection.execute("""
            SELECT id, files_json, status, stage, done, returncode,
                   created_at, updated_at, finished_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT 500
        """).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["files"] = json.loads(item.pop("files_json"))
        item["done"] = bool(item["done"])
        result.append(item)

    return jsonify(result)


@app.route("/stream/<job_id>")
def stream(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        # A persisted job from a previous server process cannot stream live events.
        return jsonify({"error": "Job is not active in this server process"}), 404

    def event_stream():
        while True:
            try:
                data = job["queue"].get(timeout=20)
                yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                if job["done"]:
                    yield "event: done\ndata: " + json.dumps({
                        "status": job["status"],
                        "returncode": job["returncode"]
                    }) + "\n\n"
                    break
            except queue.Empty:
                if job["done"]:
                    yield "event: done\ndata: " + json.dumps({
                        "status": job["status"],
                        "returncode": job["returncode"]
                    }) + "\n\n"
                    break
                yield ": keepalive\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


@app.route("/status/<job_id>")
def job_status(job_id):
    with db_connection() as connection:
        row = connection.execute(
            "SELECT id, files_json, status, stage, done, returncode, created_at, updated_at, finished_at "
            "FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()

    if row is None:
        return jsonify({"error": "Job not found"}), 404

    item = dict(row)
    item["files"] = json.loads(item.pop("files_json"))
    item["done"] = bool(item["done"])
    return jsonify(item)


initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
