"""
Read-only prehled: jak je na tom KAZDY areal s odbernymi misty
(SupplyPoint) - kolik jich ma, ktera meridla pod ne spadaji a kolik
meridel zustava nezarazenych.

Vzniklo z otazky, jestli je potreba zavest odberna mista i pro NJ, kdyz
uz jsou na FM (konverzace s Danielem 2026-08-16). Odberna mista NEMENI
rozuctovani - slouzi jen reportu Spotřeby měřidel, kde davaji dohromady
"dodáno" (privodni meridlo/faktura) proti "naměřeno" (soucet podmeru).
Bez nich spadnou vsechna meridla arealu do skupiny "Nezařazená" a
reconciliace se udelat neda.

Pouziti:
  python manage.py diag_odberna_mista
  python manage.py diag_odberna_mista --site=NJ --period=07/2026
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import Meter, Period, Site, SupplyPoint


class Command(BaseCommand):
    help = "Ukáže stav odběrných míst po areálech (co je zařazené, co visí mimo)."

    def add_arguments(self, parser):
        parser.add_argument("--site", help="Jen tenhle areál (část názvu, např. NJ).")
        parser.add_argument("--period", help="Období MM/RRRR - dopočítá i spotřeby.")

    def handle(self, *args, **options):
        period = None
        if options.get("period"):
            try:
                month, year = options["period"].split("/")
                period = Period.objects.filter(year=int(year), month=int(month)).first()
            except ValueError:
                raise CommandError("Období zadej jako MM/RRRR, např. 07/2026.")
            if period is None:
                raise CommandError(f"Období {options['period']} v databázi není.")

        sites = Site.objects.order_by("name")
        if options.get("site"):
            sites = sites.filter(name__icontains=options["site"])
        if not sites:
            raise CommandError("Žádný odpovídající areál.")

        type_labels = dict(Meter.MeterType.choices)

        for site in sites:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {site.name} ==="))
            meters = list(Meter.objects.filter(site=site).select_related("supply_point"))
            if not meters:
                self.stdout.write("  (žádná měřidla)")
                continue

            supplies = list(
                SupplyPoint.objects.filter(site=site).select_related("main_meter")
            )

            # Privodni meridla (a u virtualniho privodu i jeho slozky) nejsou
            # clenska - stejne pravidlo jako v reportu Spotřeby měřidel.
            supply_side = set()
            for sp in supplies:
                if sp.main_meter_id:
                    supply_side.add(sp.main_meter_id)
                    if sp.main_meter and sp.main_meter.is_virtual:
                        for leaf, _s in sp.main_meter.consumption_leaves():
                            supply_side.add(leaf.id)

            types = sorted({m.meter_type for m in meters})
            for mtype in types:
                type_meters = [m for m in meters if m.meter_type == mtype]
                type_supplies = [sp for sp in supplies if sp.meter_type == mtype]
                self.stdout.write(
                    f"\n  {type_labels.get(mtype, mtype)} - {len(type_meters)} měřidel, "
                    f"{len(type_supplies)} odběrných míst"
                )

                for sp in type_supplies:
                    members = [
                        m for m in type_meters
                        if m.supply_point_id == sp.id and m.id not in supply_side
                    ]
                    main = sp.main_meter.code if sp.main_meter else "— (jen z faktury)"
                    line = f"    • {sp.name}: přívod {main}, členů {len(members)}"
                    if sp.legal_loss_pct:
                        line += f", zákonná ztráta {sp.legal_loss_pct} %"
                    self.stdout.write(line)
                    if period is not None:
                        dodano = (
                            sp.main_meter.consumption_for(period) if sp.main_meter else None
                        )
                        namereno = sum(
                            (m.consumption_for(period) or Decimal("0"))
                            for m in members if not m.is_virtual
                        )
                        self.stdout.write(
                            f"        dodáno {dodano if dodano is not None else '—'} / "
                            f"naměřeno {namereno}"
                        )

                unassigned = [
                    m for m in type_meters
                    if m.supply_point_id is None and m.id not in supply_side
                ]
                if unassigned:
                    style = self.style.WARNING if type_supplies else self.style.NOTICE
                    self.stdout.write(style(
                        f"    ⚠ nezařazených měřidel: {len(unassigned)}"
                    ))
                    codes = ", ".join(sorted(m.code or m.name for m in unassigned))
                    self.stdout.write(f"        {codes}")

            if not supplies:
                self.stdout.write(self.style.WARNING(
                    "\n  → Areál nemá ŽÁDNÉ odběrné místo: v reportu Spotřeby měřidel "
                    "spadne všechno do skupiny „Nezařazená měřidla“ a nejde porovnat "
                    "dodáno vs naměřeno. Rozúčtování to ale neovlivňuje."
                ))
