"""
Diagnostika: vypise klice prvniho zaznamu evidence "adresar" (adresni
kniha) z ABRA Flexi - potrebujeme zjistit presny nazev pole s
e-mailem a nazvem firmy/osoby, nez postavime srovnavaci tabulku
s nasimi Klienty.

Pouziti:
  python manage.py diag_adresar_flexi
"""
import json

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient


class Command(BaseCommand):
    help = 'Vypíše strukturu prvního záznamu evidence "adresar" z Flexi.'

    def handle(self, *args, **options):
        try:
            flexi_client = FlexiClient()
            records = flexi_client.list_records(
                "adresar",
                extra_params={"limit": 3, "detail": "full"},
            )
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e} (FLEXI_URL, FLEXI_COMPANY, FLEXI_USER, FLEXI_PASS)")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        self.stdout.write(f"Nalezeno (vzorek) {len(records)} záznamů.\n")
        for i, rec in enumerate(records):
            self.stdout.write(self.style.WARNING(f"--- Záznam {i+1} ---"))
            for key in sorted(rec.keys()):
                value = rec[key]
                preview = json.dumps(value, ensure_ascii=False)[:100] if not isinstance(value, str) else value[:100]
                self.stdout.write(f"  {key}: {preview}")
            self.stdout.write("")
