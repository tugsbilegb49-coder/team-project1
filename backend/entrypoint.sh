#!/bin/sh
set -eu
python manage.py migrate --noinput
if [ "${DJANGO_CACHE_BACKEND:-}" = database ]; then
    python manage.py createcachetable
fi
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_WORKERS:-3}" --access-logfile - --error-logfile -
