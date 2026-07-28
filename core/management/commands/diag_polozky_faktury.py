"""
Diagnostika: zjisti, pod jakym nazvem vazby ABRA Flexi vraci polozky
(radky) vydane faktury - detail=full je nezahrnuje, jsou to vnorena
data pristupna zvlast (typicky /faktura-vydana/{id}/{vazba}.json).

Pouziti:
  python manage.py diag_polozky_faktury 11475
"""
import json

from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiAPIError, FlexiClient

CANDIDATE_RELATIONS = [
    "polozkyFaktury",
    "polozkyDokladu",
    "faktura-vydana-polozka",
    "polozky",
]


class Command(BaseCommand):
    help = "Zkusí najít vazbu s položkami vydané faktury podle ID."

    def add_arguments(self, parser):
        parser.add_argument("invoice_id", type=str)

    def handle(self, *args, **options):
        invoice_id = options["invoice_id"]

        try:
            flexi_client = FlexiClient()
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e}")

        for relation in CANDIDATE_RELATIONS:
            url = flexi_client._evidence_url(f"faktura-vydana/{invoice_id}/{relation}")
            try:
                response = flexi_client._request("GET", url)
            except FlexiAPIError as e:
                self.stdout.write(f"{relation}: chyba {e.status_code}")
                continue
            records = (response or {}).get("winstrom", {}).get(relation, [])
            self.stdout.write(self.style.SUCCESS(f"\n{relation}: {len(records)} záznamů"))
            if records:
                self.stdout.write("  klíče prvního záznamu:")
                for key in sorted(records[0].keys()):
                    value = records[0][key]
                    preview = json.dumps(value, ensure_ascii=False)[:100] if not isinstance(value, str) else value[:100]
                    self.stdout.write(f"    {key}: {preview}")
