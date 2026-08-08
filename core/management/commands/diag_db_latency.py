"""
Zmeri cistou latenci jednotlivych DB dotazu (SELECT 1) primo z appky,
stejnou privatni sitovou cestou, jakou appka bezne pouziva (PGHOST=
postgres.railway.internal) - bez Django ORM/middleware rezie, aby se
dalo overit, jestli je pomalost skutecne v siti/databazi, nebo nekde
mezi (viz konverzace s Danielem o latenci na Vyuctovani/Polozky).

Pouziti:
  python manage.py diag_db_latency
"""
import time

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Zmeri latenci N nezavislych 'SELECT 1' dotazu primo pres DB kurzor."

    def add_arguments(self, parser):
        parser.add_argument("--n", type=int, default=10, help="Pocet dotazu (vychozi 10)")

    def handle(self, *args, **options):
        n = options["n"]
        times_ms = []
        for i in range(n):
            start = time.monotonic()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            elapsed_ms = (time.monotonic() - start) * 1000
            times_ms.append(elapsed_ms)
            self.stdout.write(f"  dotaz {i + 1}: {elapsed_ms:.1f} ms")

        avg = sum(times_ms) / len(times_ms)
        self.stdout.write(self.style.SUCCESS(
            f"\nPrumer: {avg:.1f} ms | Min: {min(times_ms):.1f} ms | Max: {max(times_ms):.1f} ms"
        ))
