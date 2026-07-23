from django.core.management.base import BaseCommand, CommandError

from core.flexi_client import FlexiClient, FlexiAPIError


class Command(BaseCommand):
    help = "Vypíše neuhrazené ostatní závazky z ABRA Flexi (evidence 'zavazek')"

    def handle(self, *args, **options):
        try:
            client = FlexiClient()
            records = client.get_unpaid_other_liabilities()
        except KeyError as e:
            raise CommandError(f"Chybí env proměnná {e} (FLEXI_URL, FLEXI_COMPANY, FLEXI_USER, FLEXI_PASS)")
        except FlexiAPIError as e:
            raise CommandError(f"Flexi API chyba {e.status_code}: {e.response_body}")

        if not records:
            self.stdout.write(self.style.SUCCESS("Žádné neuhrazené ostatní závazky."))
            return

        total = sum(float(r.get("zbyvaUhradit", "0")) for r in records)

        self.stdout.write(f"{'kód':<15}{'firma':<45}{'zbývá Kč':>15}  splatnost")
        for r in sorted(records, key=lambda x: x.get("datSplat") or ""):
            kod = r.get("kod", "")
            firma = (r.get("firma@showAs") or "")[:43]
            zbyva = float(r.get("zbyvaUhradit", "0"))
            splatnost = r.get("datSplat", "")
            self.stdout.write(f"{kod:<15}{firma:<45}{zbyva:>15,.2f}  {splatnost}")

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"Počet: {len(records)}, celkem k úhradě: {total:,.2f} Kč"))
