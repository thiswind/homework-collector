# Changelog

## 2026-06-05

### Added

- Added multi-course support with a file-backed course registry under `DATA_DIR/courses.yaml`.
- Added per-course data directories for course config, roster, assignment templates, submission storage, and manifests.
- Added teacher course management pages for creating courses, editing assignment settings, managing rosters, viewing submission status, exporting CSV, and downloading ZIP bundles.
- Added per-course student flows for enrollment, login, assignment listing, PDF upload/replacement, and submission deletion.
- Added assignment template upload/download support for PDF, Office documents, PowerPoint, Excel, and ZIP files.
- Added template storage validation and tests.
- Added openEuler deployment guidance for Python 3.9, venv, gunicorn, and nginx reverse proxy.
- Added a Chinese step-by-step testing handout for manual evaluation.

### Changed

- Reworked the app from a single-course layout to a multi-course layout while keeping legacy path variables for migration compatibility.
- Updated bootstrapping so first startup creates a default course from bundled config and can seed a roster from the bundled CSV.
- Updated teacher and student routes to include `course_id` and isolate sessions by course.
- Updated documentation to reflect the current openEuler deployment path instead of the earlier Docker/Fly-oriented path.
- Updated security guidance to emphasize runtime data sensitivity and localhost-only gunicorn binding behind nginx.

### Fixed

- Fixed Python 3.9 compatibility issues for the openEuler target.
- Fixed Unicode template filename handling so uploaded Chinese filenames keep a valid extension.
- Fixed external preview access by placing nginx on port 80 in front of gunicorn and opening HTTP in firewalld.

### Verified

- Local test suite passes in the project test environment.
- The app starts successfully with gunicorn on openEuler 22.03 / Python 3.9.
- `/health` and the homepage were verified through nginx from another machine on the LAN.
