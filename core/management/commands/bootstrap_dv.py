"""
Jednorazovy bootstrap arealu DV (Dvorakova 1346/13) podle Danielova
rozpisu predepsanych plateb za 08/2026.

DV bylo v systemu skoro prazdne - mel jen plochy, zadna meridla, zadne
polozky zasobniku a jen 2 karty z 11 najemniku. Tenhle prikaz doplni:
  1. MERIDLA vody a tepla pro kazdy pronajaty prostor (kazdy byt ma
     vlastni vodomer i merak tepla - potvrdil Daniel 2026-08-24),
  2. KARTY najemniku vc. plochy a sjednaneho mesicniho najmu.

Polozky zasobniku a klice se zakladaji zvlast az podle toho, jak se maji
spolecne naklady delit (viz konverzace o zalohach).

VYCHOZI je jen NAHLED, zapisuje se az s --provest. Opakovane spusteni uz
nic nemeni (co existuje, se preskoci).

Pouziti:
  python manage.py bootstrap_dv
  python manage.py bootstrap_dv --provest
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import CardUnit, Client, ClientCard, Meter, Site, Unit

# prostor -> (cast jmena klienta, mesicni najem)
# Najmy z rozpisu 08/2026. U F1 je v rozpisu zaporne cislo (-2710), coz je
# ucetni obrat, ne najem - Daniel upresnil, ze plati 14 000 Kc/mes.
ROZPIS = [
    ("D1", None, None),                      # volny nebytovy prostor
    ("E1", "Vrzgulová", Decimal("10000")),
    ("F1", "Ptáček", Decimal("14000")),
    ("F2", "Pumrlová", Decimal("10000")),
    ("F3", "Zdráhalová", Decimal("9500")),
    ("F4", "Mostýnová", Decimal("14500")),
    ("G1", "Holan", Decimal("16000")),
    ("G2", "David", Decimal("0")),           # Danieluv vlastni byt
    ("G3", "Struhárik", Decimal("0")),       # v rozpisu bez najmu
    ("H1", "REVMA", Decimal("36000")),
    ("H2", "BATZ", Decimal("27500")),
]

PLATNOST_OD = date(2026, 1, 1)


class Command(BaseCommand):
    help = "Založí pro areál DV měřidla vody a tepla a karty nájemníků podle rozpisu plateb."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **options):
        site = Site.objects.filter(name="DV").first()
        if site is None:
            raise CommandError("Areál DV nenalezen.")
        write = options["provest"]
        if not write:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje (--provest).\n"))

        self.stdout.write(self.style.MIGRATE_HEADING("1) MĚŘIDLA (voda + teplo pro každý prostor)"))
        zalozeno_m = 0
        for prostor, jmeno, _najem in ROZPIS:
            unit = Unit.objects.filter(site=site, name=prostor).first()
            if unit is None:
                self.stdout.write(self.style.WARNING("   {} - plocha neexistuje".format(prostor)))
                continue
            for predpona, trida, jednotka, popis in (
                ("W", "voda", "m³", "vodoměr"),
                ("T", "teplo", "GJ", "měřák tepla"),
            ):
                kod = "{}_{}".format(predpona, prostor)
                if Meter.objects.filter(site=site, code=kod).exists():
                    self.stdout.write("   {:8} už existuje".format(kod))
                    continue
                self.stdout.write(self.style.SUCCESS(
                    "   {:8} {} {} ({})".format(kod, popis, prostor, jednotka)))
                if write:
                    Meter.objects.create(
                        site=site, code=kod, name="{} {}".format(popis, prostor),
                        meter_type=trida, unit_of_measure=jednotka,
                    )
                    zalozeno_m += 1

        self.stdout.write(self.style.MIGRATE_HEADING("\n2) KARTY NÁJEMNÍKŮ"))
        zalozeno_k = 0
        for prostor, jmeno, najem in ROZPIS:
            unit = Unit.objects.filter(site=site, name=prostor).first()
            if unit is None:
                continue
            if jmeno is None:
                self.stdout.write("   {:4} volný prostor - karta se nezakládá".format(prostor))
                continue
            client = Client.objects.filter(name__icontains=jmeno).first()
            if client is None:
                self.stdout.write(self.style.WARNING(
                    "   {:4} klient podle '{}' nenalezen".format(prostor, jmeno)))
                continue
            if CardUnit.objects.filter(card__client=client, unit=unit).exists():
                self.stdout.write("   {:4} {:26} karta už existuje".format(prostor, client.name[:26]))
                continue

            popis = "Karta {} DV".format(client.code or client.name[:10])
            self.stdout.write(self.style.SUCCESS(
                "   {:4} {:26} {:>9,.0f} Kč/měs   {}".format(
                    prostor, client.name[:26], najem, popis)))
            if write:
                card = ClientCard.objects.create(
                    client=client, unit=unit, description=popis, valid_from=PLATNOST_OD,
                )
                CardUnit.objects.create(
                    card=card, unit=unit,
                    monthly_rent_override=najem if najem else None,
                )
                zalozeno_k += 1

        if write:
            self.stdout.write(self.style.SUCCESS(
                "\nzaloženo {} měřidel a {} karet".format(zalozeno_m, zalozeno_k)))
        else:
            self.stdout.write(self.style.WARNING("\nNic zapsáno nebylo (--provest)."))
        self.stdout.write(
            "\nDál je potřeba založit položky zásobníku (voda, teplo, společná "
            "elektřina, výtah, úklid) a klíče - to zvlášť, až bude jasné dělení."
        )
