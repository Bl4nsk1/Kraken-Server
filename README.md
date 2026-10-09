<p align="center">
  <img width="400" height="400" alt="kraken-logo" src="https://github.com/user-attachments/assets/bb4a7b65-b003-4c66-a6c9-05417b14c7ff" />
</p>

<p align="center">
  <b>Automated Wi-Fi Handshake Processing & Password Cracking</b><br>
  Upload your PCAPs and let Kraken handle the rest.
</p>

# Kraken-Server-Server

**Kraken-Server-Server** is a Flask-based web application for managing wireless capture files and automating their cracking through Cap2Hash and Hashcat.

It provides a web interface for uploading capture files, monitoring processing jobs in real time, and reviewing execution logs and job history.

> **Status:** Under development.

## Features

* **Web interface:** Upload and manage capture files through a browser.
* **Multiple file uploads:** Submit multiple supported capture files in a single request.
* **Automated processing:** Integrate Cap2Hash and HashCater to convert and process capture files.
* **Background jobs:** Execute long-running tasks without blocking the web interface.
* **Real-time updates:** Receive job events through Server-Sent Events (SSE).
* **Persistent job history:** Store job metadata in an SQLite database.
* **Execution logs:** Save individual logs for later inspection.
* **Job details:** Review processing status, timestamps, return codes, and execution output.
* **JSON API:** Retrieve job history programmatically.

## Architecture

Kraken-Server-Server uses Flask to serve the web interface and coordinate background processing.

```text
Browser
   |
   v
Flask Application
   |
   +---- File Upload
   |
   +---- Job Creation
   |        |
   |        +---- SQLite Database
   |        +---- Job Log
   |
   +---- Background Worker
             |
             +---- Cap2Hash
             |
             +---- HashCater
                       |
                       +---- Hashcat

Browser <---- Server-Sent Events (SSE)
Browser <---- Job History / Job Details
```

### Job lifecycle

Each submitted job is assigned a unique identifier and tracked through its execution lifecycle.

1. **Queued:** The job has been created and registered.
2. **Running:** Processing is underway.
3. **Completed:** The processing workflow finished successfully.
4. **Failed:** A processing stage returned an error or could not start.

Job metadata is stored in SQLite, while execution output is written to a separate log file.

> Jobs that were running when the application stopped require recovery handling; persistent metadata alone does not resume their processes.

## Requirements

Before installing Kraken-Server, ensure the following components are available:

* Python 3.10 or later (recommended; verify compatibility with your environment).
* pip.
* Bash.
* `stdbuf`, usually provided by GNU coreutils.
* Flask.
* Cap2Hash.
* HashCater.
* Hashcat.
* A Linux environment or another environment compatible with the configured scripts and command-line tools.

Hardware acceleration depends on the installed Hashcat backend and supported hardware. A working web interface does not guarantee that GPU acceleration is configured correctly.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Bl4nsk1/Kraken-Server.git
cd Kraken-Server
```

Replace the repository URL if your GitHub repository uses a different name or owner.

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

Create a `requirements.txt` file containing the Python dependencies used by the project. At minimum, the application requires Flask.

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Cap2Hash and HashCater scripts

Clone the projects repositories.

```bash
git clone https://github.com/Bl4nsk1/Cap2Hash
git clone https://github.com/Bl4nsk1/HashCater
```
Configure the variables of each script.

## Configuration

Kraken-Server requires local paths to its upload directory, processing scripts, and Hashcat executable.

Open `server.py` and configure the following variables:

```python
UPLOAD_FOLDER = ""
CAP2HASH_SCRIPT = ""
HASHCATER_SCRIPT = ""
HASHCAT_PATH = ""
```

Replace the empty strings with paths appropriate for your environment.

| Variable           | Description                                                        | Example                       |
| ------------------ | ------------------------------------------------------------------ | ----------------------------- |
| `UPLOAD_FOLDER`    | Directory used for uploaded capture files and generated hash files | `/home/user/handshakes`       |
| `CAP2HASH_SCRIPT`  | Absolute path to the Cap2Hash script                               | `/opt/Cap2Hash/Cap2Hash.sh`   |
| `HASHCATER_SCRIPT` | Absolute path to the HashCater script                              | `/opt/HashCater/HashCater.sh` |
| `HASHCAT_PATH`     | Path to the Hashcat executable                                     | `/usr/bin/hashcat`            |

The paths above are examples only. Use the actual paths on your system.

Ensure that:

* The upload directory exists and is writable by the application.
* Both shell scripts exist and are readable.
* Hashcat is installed and executable.
* The user running Flask has the required permissions.
* All required command-line dependencies are installed.

Kraken-Server stores its persistent application data relative to `server.py`:

```text
Kraken-Server_data/
├── jobs.sqlite3
└── jobs/
    ├── <job-id>.log
    └── ...
```

This directory is generated at runtime. Do not commit its contents to the repository.

## Running the application

Start the Flask application:

```bash
python server.py
```

By default, the application listens on port `5000`.

Open the following address in your browser:

```text
http://127.0.0.1:5000
```

The application currently binds to `0.0.0.0`, which makes it listen on all available network interfaces. Do not expose it to an untrusted network without implementing appropriate authentication, authorization, and deployment security controls.

## Web interface

### Upload

The main page allows users to upload supported capture files.

Supported file extensions:

* `.pcap`
* `.cap`
* `.pcapng`

After submission, Kraken-Server creates a job and starts background processing.

### Job monitoring

The job monitoring interface receives events using Server-Sent Events (SSE), allowing the browser to display execution output while processing continues.

### History

The history page lists previously registered jobs, including their status and timestamps.

### Job details

The job details page displays stored metadata and the corresponding execution log when available.

## API endpoints

| Method | Endpoint           | Description                         |
| ------ | ------------------ | ----------------------------------- |
| `GET`  | `/`                | Display the upload interface        |
| `POST` | `/`                | Submit capture files for processing |
| `GET`  | `/history`         | Display persistent job history      |
| `GET`  | `/jobs/<job_id>`   | Display a job's details and log     |
| `GET`  | `/api/jobs`        | Return recent jobs as JSON          |
| `GET`  | `/status/<job_id>` | Return a job's persisted status     |
| `GET`  | `/stream/<job_id>` | Stream live job events through SSE  |

The history and API endpoints currently return up to 500 jobs.

A job's live event stream is maintained in application memory. Previously persisted jobs remain available through the history and status endpoints, but their original live streams are not restored after a server restart.

## Data and logs

Kraken-Server uses SQLite to store job metadata, including:

* Job identifier.
* Uploaded filenames.
* Current status and processing stage.
* Return code.
* Creation and update timestamps.
* Completion timestamp.

Execution logs are stored separately under `Kraken-Server_data/jobs/`.

Back up the SQLite database and relevant logs if you need to preserve execution history. Avoid publishing logs or capture data containing information that should remain private.

## Security considerations

Kraken-Server is a development project and should be deployed carefully.

* Do not expose the application directly to the public Internet without access controls.
* Do not commit capture files, generated hashes, logs, databases, or local configuration.
* Restrict filesystem permissions for the upload and data directories.
* Set upload size and quantity limits before accepting untrusted files.
* Consider per-job directories to prevent concurrent jobs from processing one another's files.
* Add exception handling and recovery for interrupted jobs.
* Limit concurrent processing and subprocess resource consumption.
* Use least-privilege permissions for the Flask application and processing scripts.

**Current implementation limitation:** uploaded files and generated hash files use a shared upload directory. Concurrent jobs may interfere with one another, and older `.hc22000` files may be included in later processing runs. Per-job isolation should be implemented before using the application for concurrent or untrusted workloads.

## Troubleshooting

### The application fails to start

Verify that the configured directories exist and that the Python environment contains Flask.

### A processing script fails to start

Check the configured script paths, Bash availability, file permissions, and dependencies.

### No `.hc22000` files are found

Confirm that Cap2Hash completed successfully and that generated files are present in the configured upload directory.

### Live updates stop working

Check that the browser is connected to the correct job stream and that any reverse proxy forwards SSE responses without buffering them.

### Hashcat does not detect the GPU

Run Hashcat's device discovery command independently:

```bash
hashcat -I
```

Check the installed drivers, supported backend, and device permissions. GPU detection is an environment-level issue separate from Flask job tracking.

## Roadmap

Potential improvements include:

* [ ] Per-job file isolation.
* [ ] Configurable paths through environment variables.
* [ ] Startup validation for missing configuration.
* [ ] Upload size and quantity limits.
* [ ] Job recovery after application restarts.
* [ ] Better subprocess exception handling and cancellation.
* [ ] Authentication and authorization.
* [ ] Log rotation and retention policies.
* [ ] Automated tests for uploads, processing, and persistence.
* [ ] Containerized deployment.
* [ ] Improved GPU status reporting.

## Contributing

Contributions, bug reports, and suggestions are welcome.

When submitting changes, please include a clear description of the problem or feature, the changes made, and the tests performed.

## Disclaimer

Kraken-Server is intended for authorized security research, testing, and educational use. Only process capture files and networks for which you have explicit authorization.

The project does not grant permission to access, audit, or recover credentials from third-party networks or devices.

## 📜 License

MIT License

Copyright (c) 2026 Bl4nsk1

## 👤 Author

[Bl4nsk1](https://github.com/Bl4nsk1)
