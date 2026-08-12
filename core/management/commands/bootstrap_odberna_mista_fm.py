"""
Jednorazovy bootstrap (idempotentni): zalozi pro areal FM dve elektro
odberna mista a napoji na ne, co uz vime:

  - "EAN 668"                -> privodni meridlo 668_CELKEM (dodano),
                               clenska meridla E_M1, E_N4
  - "Hlavni odber elektro FM" -> bez privodniho meridla (dodano jen z
                               faktury), clenska meridla priradis sam
                               (hromadnou akci v seznamu meridel)

Zbytek meridel NECHAVA nezarazeny zamerne - topologii (ktere meridlo
pod ktery odber) doplni Daniel, reconciliacni prehled mu k tomu slouzi.
Spousteni opakovane nic nerozbije (get_or_create, prirazeni jen doplni).

Pouziti:
  python manage.py bootstrap_odberna_mista_fm
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Meter, Site, SupplyPoint

MEMBERS_668 = ["E_M1", "E_N4"]


class Command(BaseCommand):
    help = "Založí FM elektro odběrná místa (EAN 668 + Hlavní odběr FM) a napojí známá měřidla."

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains="FM").first()
        if site is None:
            raise CommandError("Areál 'FM' nenalezen.")

        main_668 = Meter.objects.filter(site=site, code="668_CELKEM").first()
        if main_668 is None:
            self.stdout.write(self.style.WARNING(
                "  Měřidlo 668_CELKEM nenalezeno - EAN 668 založím bez přívodního měřidla, doplň ručně."
            ))

        ean668, created = SupplyPoint.objects.get_or_create(
            site=site, name="EAN 668",
            defaults={"meter_type": Meter.MeterType.ELECTRICITY, "main_meter": main_668},
        )
        self.stdout.write(self.style.SUCCESS(
            f"  EAN 668: {'založeno' if created else 'už existuje'} (id={ean668.pk})"
        ))
        if main_668 is not None and ean668.main_meter_id != main_668.id:
            ean668.main_meter = main_668
            ean668.save(update_fields=["main_meter"])
            self.stdout.write("    -> přívodní měřidlo nastaveno na 668_CELKEM")

        hlavni_fm, created = SupplyPoint.objects.get_or_create(
            site=site, name="Hlavní odběr elektro FM",
            defaults={"meter_type": Meter.MeterType.ELECTRICITY},
        )
        self.stdout.write(self.style.SUCCESS(
            f"  Hlavní odběr elektro FM: {'založeno' if created else 'už existuje'} "
            f"(id={hlavni_fm.pk}, bez přívodního měřidla - dodáno z faktury)"
        ))

        for code in MEMBERS_668:
            meter = Meter.objects.filter(site=site, code=code).first()
            if meter is None:
                self.stdout.write(self.style.WARNING(f"    měřidlo {code} nenalezeno - přeskočeno"))
                continue
            if meter.supply_point_id != ean668.id:
                meter.supply_point = ean668
                meter.save(update_fields=["supply_point"])
                self.stdout.write(f"    {code} -> EAN 668")
            else:
                self.stdout.write(f"    {code} už je na EAN 668")

        unassigned = Meter.objects.filter(
            site=site, meter_type=Meter.MeterType.ELECTRICITY, supply_point__isnull=True,
        ).count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n  Hotovo. Nezařazených FM elektro měřidel zbývá: {unassigned} "
            f"(přiřaď hromadnou akcí 'Přiřadit vybraná měřidla k odběrnému místu')."
        ))
