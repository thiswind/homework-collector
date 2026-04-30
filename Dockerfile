FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV ROSTER_PATH=/data/roster.csv
ENV STORAGE_ROOT=/data/storage
ENV COURSE_CONFIG=/data/course.yaml

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config
COPY wsgi.py .
COPY 点名册.csv ./

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "wsgi:application"]
