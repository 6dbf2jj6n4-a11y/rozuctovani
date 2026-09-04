FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# build 2
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PGHOST_DEFAULT=postgres.railway.internal

# --workers 3 --threads 2 --worker-class gthread: bez techto voleb
# gunicorn defaultne pouzije jen 1 worker/sync tridu (--threads bez
# --worker-class gthread se tise ignoruje), takze umi obslouzit jen
# JEDEN pozadavek najednou - jakykoliv pomalejsi request (napr. report
# prochazejici hodne polozek) tim zablokuje uplne vse ostatni v adminu,
# i bezne seznamy. Viz konverzace s Danielem - "uplne vsechno pomale"
# i po vypnuti DEBUG (druha pricina byl chybejici CONN_MAX_AGE, viz
# config/settings.py).
#
# --timeout 300: gunicorn defaultne utne request po 30 s. Tlacitko
# "Zkontrolovat rizika (ARES)" nad seznamem Klientu se pta ARESu na
# kazdeho klienta zvlast (viz core/rizika.py), takze bezne bezi dele -
# s 30 s by worker spadl a uzivatel by videl jen 502.
CMD echo "PGHOST=$PGHOST PGUSER=$PGUSER" && python manage.py migrate --noinput && python manage.py ensure_superuser && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --threads 2 --worker-class gthread --timeout 300
