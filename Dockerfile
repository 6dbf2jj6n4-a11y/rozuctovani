FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# build 2
# cache-bust 2026-07-25b - Railway opakovane znovupouzival stary cache image
# i pres nove commity (SITE_SUBHEADER se nikdy nenasadilo) - tenhle radek
# vynuti skutecny rebuild od tohoto bodu dal.
RUN echo "cachebust-2026-07-25b"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PGHOST_DEFAULT=postgres.railway.internal

CMD echo "PGHOST=$PGHOST PGUSER=$PGUSER" && python manage.py migrate --noinput && python manage.py ensure_superuser && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
