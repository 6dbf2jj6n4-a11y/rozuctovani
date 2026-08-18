"""
Zalozi odberna mista (SupplyPoint) pro libovolny areal podle toho, co uz
je v datech - obecna varianta bootstrap_odberna_mista_fm, ktery ma kody
meridel natvrdo. Vzniklo pro NJ, aby mel stejny model jako FM
(konverzace s Danielem 2026-08-16).

Co dela, pro kazdy typ meridla v arealu zvlast:
  1. najde polozku zasobniku "hlavní odběr ..." odpovidajici tridy,
  2. zalozi odberne misto pojmenovane podle ni (nebo genericky),
  3. jako privodni meridlo vezme hlavni meridlo te polozky
     (ServicePoolItem.meter); kdyz zadne nema, necha prazdne =
     "dodano" se bere z faktury, presne jako Hlavni odber elektro FM,
  4. pod odberne misto priradi meridla toho typu, ktera jeste zadne
     nemaji - krome privodniho meridla a (u virtualniho privodu) jeho
     slozek, ty patri k dodavce, ne mezi podmery.

VYCHOZI je jen NAHLED. Zapisuje se az s --provest. Opakovane spusteni
nic nerozbije (get_or_create, prirazuje jen to, co je zatim bez
odberneho mista - rucni zarazeni tedy nikdy neprepise).

Pouziti:
  python manage.py bootstrap_odberna_mista --site=NJ
  python manage.py bootstrap_odberna_mista --site=NJ --provest
  python manage.py bootstrap_odberna_mista --site=NJ --typ=electricity --provest
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import InvoiceClassColor, Meter, ServicePoolItem, Site, SupplyPoint


class Command(BaseCommand):
    help = "Založí odběrná místa pro areál podle položek zásobníku a přiřadí volná měřidla."

    def add_arguments(self, parser):
        parser.add_argument("--site", required=True, help="Areál (část názvu, např. NJ).")
        parser.add_argument("--typ", help="Jen tenhle typ měřidla (electricity/water/heat/gas/other).")
        parser.add_argument(
            "--provest", action="store_true",
            help="Skutečně zapsat. Bez tohohle jde jen o náhled.",
        )

    def handle(self, *args, **options):
        site = Site.objects.filter(name__icontains=options["site"]).first()
        if site is None:
            raise CommandError(f"Areál podle '{options['site']}' nenalezen.")

        write = options["provest"]
        if not write:
            self.stdout.write(self.style.WARNING(
                "NÁHLED - nic se nezapisuje. Pro provedení přidej --provest.\n"
            ))

        meters = list(Meter.objects.filter(site=site))
        if not meters:
            raise CommandError(f"Areál {site.name} nemá žádná měřidla.")

        types = sorted({m.meter_type for m in meters})
        if options.get("typ"):
            if options["typ"] not in types:
                raise CommandError(
                    f"Typ '{options['typ']}' v areálu {site.name} není. Dostupné: {', '.join(types)}"
                )
            types = [options["typ"]]

        type_labels = InvoiceClassColor.label_map()
        self.stdout.write(self.style.MIGRATE_HEADING(f"=== {site.name} ==="))

        for mtype in types:
            label = type_labels.get(mtype, mtype)
            self.stdout.write(f"\n{label}:")

            # Meridlo uz drzi primo kod Tridy (drive samostatny Typ meridla).
            invoice_class = mtype or "ostatni"
            item = ServicePoolItem.objects.filter(
                site=site, invoice_class=invoice_class, name__icontains="hlavní odběr"
            ).select_related("meter").first()

            if item is not None:
                name = item.name[:1].upper() + item.name[1:]
                main_meter = item.meter
                self.stdout.write(f"  položka zásobníku: {item.name}")
            else:
                name = f"Hlavní odběr {label.lower()} {site.name}"
                main_meter = None
                self.stdout.write(self.style.WARNING(
                    "  položka zásobníku 'hlavní odběr ...' nenalezena - odběrné místo "
                    f"pojmenuju '{name}'"
                ))

            existing = SupplyPoint.objects.filter(site=site, name=name).first()
            if existing is not None:
                supply = existing
                self.stdout.write(f"  odběrné místo '{name}' už existuje (id={supply.pk})")
            elif write:
                supply = SupplyPoint.objects.create(
                    site=site, name=name, meter_type=mtype, main_meter=main_meter,
                )
                self.stdout.write(self.style.SUCCESS(f"  odběrné místo '{name}' založeno (id={supply.pk})"))
            else:
                supply = None
                self.stdout.write(self.style.SUCCESS(f"  + založit odběrné místo '{name}'"))

            self.stdout.write(
                f"  přívodní měřidlo: {main_meter.code if main_meter else '— (dodáno z faktury)'}"
            )
            if supply is not None and main_meter is not None and supply.main_meter_id != main_meter.id:
                if write:
                    supply.main_meter = main_meter
                    supply.save(update_fields=["main_meter"])
                self.stdout.write(f"    -> přívodní měřidlo nastaveno na {main_meter.code}")

            # Privodni meridlo (a u virtualniho i jeho slozky) nejsou podmery.
            supply_side = set()
            if main_meter is not None:
                supply_side.add(main_meter.id)
                if main_meter.is_virtual:
                    for leaf, _s in main_meter.consumption_leaves():
                        supply_side.add(leaf.id)

            volna = [
                m for m in meters
                if m.meter_type == mtype and m.supply_point_id is None
                and m.id not in supply_side
            ]
            if not volna:
                self.stdout.write("  žádná volná měřidla k přiřazení")
                continue

            self.stdout.write(f"  měřidel k přiřazení: {len(volna)}")
            for m in sorted(volna, key=lambda x: x.code or x.name):
                znacka = " (virtuální)" if m.is_virtual else ""
                self.stdout.write(f"    {m.code or m.name}{znacka}")
            if write and supply is not None:
                Meter.objects.filter(id__in=[m.id for m in volna]).update(supply_point=supply)
                self.stdout.write(self.style.SUCCESS(f"  -> přiřazeno pod '{name}'"))

        if not write:
            self.stdout.write(self.style.WARNING(
                "\nNic zapsáno nebylo. Až to bude sedět, spusť znovu s --provest."
            ))
        self.stdout.write(
            "\nPotom si výsledek zkontroluj reportem Spotřeby měřidel, "
            "nebo příkazem diag_odberna_mista."
        )
