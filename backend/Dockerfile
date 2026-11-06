FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 && rm -rf /var/lib/apt/lists/*
COPY . .
RUN useradd --create-home app && mkdir -p /app/backups /app/staticfiles && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["sh", "entrypoint.sh"]
