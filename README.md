# Homework Collector

File-backed Flask web app for course homework PDF collection (no SQL database). See `cursor-agent-team/ai_workspace/plans/PLAN-B-001.md` for full specification; follow-up **teacher course editor** in `cursor-agent-team/ai_workspace/plans/PLAN-B-002.md`.

## Source repository

- **Public GitHub**: https://github.com/thiswind/homework-collector  
- Default branch: `master`. **Never commit** `.env`, `data/`, or Fly/teacher secrets — use `flyctl secrets set` and `.gitignore`.

## Course configuration (teacher UI)

- Runtime **`course.yaml`** defaults to **`$DATA_DIR/course.yaml`** (same persistent directory as `roster.csv` and `storage/` on Fly). Override with env **`COURSE_CONFIG`**.
- On first boot, if that file is missing, the app copies the bundled template from `config/course.yaml` in the image.
- After **teacher login** → **课程与作业设置** → edit `course_id`, course title, and each assignment (`id` + display title). Changing an assignment **id** does not delete old `storage/<old_id>/` folders automatically.

## Runtime

- Python 3.12+
- Dependencies: `requirements.txt`

## Local development

```bash
conda activate base
pip install -r requirements-dev.txt
export SECRET_KEY="dev-secret"
export TEACHER_PASSWORD="your-teacher-password"
flask --app app:create_app run --debug
```

Open http://127.0.0.1:5000 — health check: http://127.0.0.1:5000/health

## Tests

```bash
pytest
```

## Docker (production-like)

```bash
docker build -t homework-collector .
mkdir -p data
docker run --rm -d --name hc-local -p 8080:8080 \
  -v "$(pwd)/data:/data" \
  -e SECRET_KEY=replace-me \
  -e TEACHER_PASSWORD=replace-teacher \
  homework-collector
curl -sfS http://127.0.0.1:8080/health
docker rm -f hc-local
```

Persistent roster and uploads live under `DATA_DIR` (default `/data` in the image). Mount a host directory to `/data` for local smoke tests so `roster.csv` survives container restarts.

## Fly.io (Phase I)

1. `flyctl auth login` then `flyctl auth whoami`
2. Edit `fly.toml` — set unique `app` name; adjust `primary_region` if needed
3. Create an app: `flyctl apps create <name>`
4. Create a volume for persistent roster/storage: `flyctl volumes create homework_data --region sin --size 1 -a <app>`
5. Volume mount is already declared in `fly.toml` (`[[mounts]]` → `/data`). If you previously created `homework_data` in another region (e.g. `nrt`), create a **new** volume in `sin` for this app; Fly volumes are region-bound.
6. Set secrets: `flyctl secrets set SECRET_KEY=... TEACHER_PASSWORD=...`
7. `flyctl deploy` — if the **remote builder** stalls or errors (e.g. depot handshake / deadline exceeded), retry with **`flyctl deploy --local-only`** (requires local Docker such as OrbStack).
8. **Single Machine in `sin`**: run `flyctl machines list`; if more than one Machine is running, run `flyctl scale count 1 --region sin --yes` (or remove extra machines per Fly docs).
9. Verify: `curl -sfS https://<app>.fly.dev/health`

### Fly acceptance checklist (product owner / UAT on HTTPS only)

1. `curl -sfS https://<app>.fly.dev/health` returns JSON with `"status":"ok"`.
2. Open `https://<app>.fly.dev/` in a browser; no TLS warnings.
3. Teacher login with secrets you set via `flyctl secrets set`.
4. Optional: student enroll → upload PDF → teacher ZIP download (see manual E2E below).

Automated gates (pytest, `docker build` / local `curl`) are run on the implementation machine or CI; **final sign-off is this HTTPS checklist**, not localhost.

### Fly verification (manual E2E)

1. Open `https://<app>.fly.dev/`
2. Teacher login → download roster template → optional import
3. Student: enroll with valid 学号+姓名 from roster → save one-time password
4. Student: login → upload PDF for hw01
5. Teacher: download ZIP for hw01 → contains `pdfs/` PDFs + `ledger.csv`

## Environment variables

See `.env.example`. Critical: `SECRET_KEY`, `TEACHER_USERNAME`, `TEACHER_PASSWORD`, **`COURSE_CONFIG`** (optional; defaults to `DATA_DIR/course.yaml`), paths under `DATA_DIR` on persistent disk for Fly.

## Tooling versions (recorded at implementation)

- Python 3.12
- Flask 3.x, Flask-WTF 1.3.x
- Docker base `python:3.12-slim-bookworm`
