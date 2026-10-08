# Changelog

All notable changes to **KRAKEN** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to Semantic Versioning where applicable.

## [Unreleased]

### Added

* Persistent job history using SQLite.
* Individual log files for job execution, stored on disk.
* Job history page accessible through `/history`.
* Detailed job inspection page with execution metadata and logs.
* JSON API endpoint at `/api/jobs` for retrieving job history.
* Job status persistence across Flask application restarts.
* Real-time job progress and event streaming using Server-Sent Events (SSE).

### Changed

* Updated job status retrieval to use persistent database records.
* Improved visibility into processing stages and execution output.
* Integrated job metadata and execution logs into the history workflow.

### Technical Details

* Flask web application.
* SQLite database for persistent job metadata.
* Background job execution using Python threads.
* Queue-based event handling.
* Cap2Hash integration for capture file conversion.
* Hashcat integration for hash processing.
* Persistent application data stored in `kraken_data/`.

### Notes

* Existing `index.html` and `sucess.html` templates are retained.
* Jobs executed before persistent history was introduced may not be available in the database.
* Upload files currently use a shared directory; per-job file isolation remains a future improvement.
* Hardware acceleration depends on the host's Hashcat and GPU configuration.

## [0.1.0] - Initial Development

### Added

* Initial Flask web interface.
* File upload workflow for capture files.
* Integration with Cap2Hash for conversion to Hashcat-compatible formats.
* Hashcat execution workflow.
* Background processing for long-running tasks.
* Initial job status tracking.
* Terminal-style web interface.

---

[Unreleased]: https://github.com/Bl4nsk1/KRAKEN/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Bl4nsk1/KRAKEN/releases/tag/v0.1.0
