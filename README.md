# Homework Collector

File-backed Flask web app for collecting course homework PDFs. It supports multiple courses without a SQL database: each course has its own roster, assignment config, templates, uploads, and submission manifests.

## Data layout

Runtime state lives under `DATA_DIR`:

```text
DATA_DIR/
  courses.yaml
  courses/
    <course_id>/
      course.yaml
      roster.csv
      templates/
        <assignment_id>/
          <template file>
      storage/
        <assignment_id>/
          _manifest.json
          *.pdf
```

On first boot, the app creates a default course from `config/course.yaml` and seeds `roster.csv` from `点名册.csv` when present.

## Main workflows

- Home page lists active courses.
- Student enters a course, registers once with 学号+姓名, receives a one-time initial password, then logs in to upload or replace PDF submissions.
- Teacher logs in globally, creates courses, manages each course roster, edits assignments, uploads assignment templates, views submission status, exports CSV, and downloads ZIP bundles.

Assignment templates support `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, and `.zip`.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY="dev-secret"
export TEACHER_PASSWORD="your-teacher-password"
flask --app app:create_app run --debug
```

Open `http://127.0.0.1:5000`; health check: `http://127.0.0.1:5000/health`.

## Tests

```bash
pytest
```

## Environment variables

See `.env.example`. Important production values:

- `SECRET_KEY`: strong random Flask secret.
- `TEACHER_USERNAME`: teacher login username, default `teacher`.
- `TEACHER_PASSWORD`: strong teacher password; never commit it.
- `DATA_DIR`: persistent data directory.
- `MAX_UPLOAD_MB`: student PDF upload size limit, default `20`.
- `MAX_TEMPLATE_MB`: assignment template size limit, default `50`.
- `PERMANENT_SESSION_LIFETIME`: session lifetime in seconds, default `28800`.

Legacy single-course path variables remain for migration compatibility, but new course operations use the `DATA_DIR/courses/` layout.

## openEuler server deployment

Verified target shape: openEuler 22.03, Python 3.9, nginx, systemd, no Docker/Podman, no git. Deploy by source tarball and run with venv + gunicorn behind nginx.

Non-destructive application smoke command pattern:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn
env DATA_DIR=/home/thiswind/homework-data \
  SECRET_KEY='replace-with-strong-random' \
  TEACHER_PASSWORD='replace-with-strong-password' \
  .venv/bin/gunicorn -b 127.0.0.1:18080 'app:create_app()'
```

Then verify from the server:

```bash
curl -sfS http://127.0.0.1:18080/health
```

Installing a permanent systemd service or nginx reverse proxy requires root/sudo approval and should not be done blindly. Recommended production bind is `127.0.0.1:18080`, with nginx proxying public port 80 to that local port.

## Docker/Fly notes

The repository still contains Docker/Fly files from the original deployment path, but the current openEuler target uses venv + gunicorn + nginx because Docker/Podman are not installed on the server.

## Security notes

Do not commit `.env`, `data/`, runtime course data, student submissions, or production secrets. Set `SECRET_KEY` and `TEACHER_PASSWORD` through the deployment environment.
