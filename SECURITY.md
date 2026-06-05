# Security Policy

This project stores course rosters, password hashes, assignment templates, and student submissions on disk. Treat the runtime data directory as sensitive.

## Supported versions

Security fixes are applied to the current `master` branch of this repository.

## Reporting vulnerabilities

Report vulnerabilities privately to the repository owner or maintainer. Do not publish student data, teacher credentials, `.env` files, submission archives, or screenshots containing real rosters in public issues.

## Operational requirements

- Set a strong `SECRET_KEY` in production.
- Set a strong `TEACHER_PASSWORD` outside the repository.
- Never commit `.env`, `data/`, runtime course directories, rosters, templates, or submissions.
- Restrict filesystem access to `DATA_DIR` on the server.
- Run the app behind HTTPS or a trusted reverse proxy for real deployments.
- Do not expose the gunicorn port publicly; bind it to `127.0.0.1` and proxy through nginx.
