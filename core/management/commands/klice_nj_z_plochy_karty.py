"""
NJ: vaha klicu, ktere se deli podle vymery, se bere z Ploch Karty.

Daniel 2026-09-16 porovnal klice v NJ se starou aplikaci. U vetsiny karet
rucne zadana vymera na Plochy karty sedela presne - ale tam, kde se
plochy prehazovaly mezi najemci, klic utekl a nikdo si toho nevsiml:

  * CALAMARI #73: srazkove 248 misto 261 m2 (hlavni klic se rucne snizil
    o 13 m2, ktere si vzalo KJO, a zaroven se ta plocha z Karty odebrala -
    odectlo se to dvakrat), stejne tak snih 248, ostraha 223, uklid 248
    a odpad dokonce jen 25 (hlavni klic chybel uplne, zbyly jen dva
    automaticke ke konkretnim Plocham).
  * Snih mel u Makera, MastrCrane a Gnese vahu 1 misto 40 / 14 / 14 m2.

Reseni je nedrzet stejne cislo na dvou mistech: klic dostane
weight_source = "plocha" (AllocationKey.ZdrojVahy.PLOCHA) a vahu si bere
primo z Karty. Engine zapocita odvozenou vahu jednou za Kartu a polozku,
takze ani vic klicu na jedne karte nic nezdvoji.

Zaroven se uklidi klice, ktere vznikly automaticky k jednotlivym Plocham -
po prepnuti jsou zbytecne a na Karte by matly (tri radky po 261 m2).
Smazou se jen tehdy, kdyz maji stejne priznaky Fakturovat / Odecist jako
klic, ktery zustava; jinak se necha vse a vypise varovani.

POZOR - polozky, ktere se NEDELI podle vymery, sem nepatri:
  * hlavni odber voda NJ - vahou je POCET OSOB (tam se jen jednorazove
    smazaly automaticke klice k Plocham, viz historie prikazu),
  * internet / revize hasicich pristroju - pevne castky,
  * pult ochrany ALSYKO - vaha 1 za Kartu.

Prikaz je OPAKOVATELNY - druhe spusteni uz nema co menit.

Pouziti:
  python manage.py klice_nj_z_plochy_karty            # jen ukaze
  python manage.py klice_nj_z_plochy_karty --provest  # zapise
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AllocationKey, ServicePoolItem, Site

# Polozky NJ, jejichz vahou je vymera pronajate plochy.
POLOZKY = (
    "srážkové vody NJ",
    "odklizení sněhu v zimních obdobích",
    "odvoz komunálního odpadu NJ",
    "ostraha areálu NJ",
    "úklidové služby společných prostor NJ",
)


class Command(BaseCommand):
    help = "NJ: váha klíčů dělených podle výměry se bere z Ploch karty."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        zapsat = volby["provest"]
        site = Site.objects.filter(name="NJ").first()
        if site is None:
            raise CommandError("Areál NJ neexistuje.")
        polozky = []
        for nazev in POLOZKY:
            polozka = ServicePoolItem.objects.filter(site=site, name=nazev).first()
            if polozka is None:
                raise CommandError(f"Položka „{nazev}“ v areálu NJ neexistuje.")
            polozky.append(polozka)

        if not zapsat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje, spusť s --provest.\n"))

        prepnout, smazat, sporne = [], [], []

        for polozka in polozky:
            podle_karty = {}
            for klic in AllocationKey.objects.filter(
                service_item=polozka
            ).select_related("client_card__client", "unit"):
                podle_karty.setdefault(klic.client_card_id, []).append(klic)

            for klice in podle_karty.values():
                # Zustava klic bez Plochy (soucтovy), jinak ten nejstarsi.
                bez_plochy = [k for k in klice if k.unit_id is None]
                zustava = min(bez_plochy or klice, key=lambda k: k.pk)
                for klic in klice:
                    if klic is zustava:
                        continue
                    if (klic.is_billed, klic.deduct_from_pool) != (zustava.is_billed, zustava.deduct_from_pool):
                        sporne.append((klic, zustava))
                    else:
                        smazat.append(klic)
                if (zustava.weight_source != AllocationKey.ZdrojVahy.PLOCHA
                        or zustava.value is not None or zustava.unit_id is not None):
                    prepnout.append((zustava, zustava.value, zustava.client_card.plocha_celkem))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Váha z Plochy karty ({len(prepnout)} klíčů):"))
        for klic, stara, nova in sorted(prepnout, key=lambda z: (z[0].service_item.name, str(z[0].client_card))):
            # stara is None = klic uz vahu z Karty bere, jen se mu ruší
            # vazba na jednu Plochu - vaha se tim nemeni.
            zmena = "" if stara is None or stara == nova else self.style.WARNING("   <- MĚNÍ SE")
            self.stdout.write(
                f"   {klic.service_item.name[:30]:30} karta #{klic.client_card_id:<4} "
                f"{str(klic.client_card)[:28]:28} {stara} -> {nova} m²{zmena}"
            )

        if smazat:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nSmazat klíče navázané na jednotlivé Plochy ({len(smazat)}):"))
            for klic in smazat:
                self.stdout.write(
                    f"   klíč #{klic.pk:<5} {klic.service_item.name[:30]:30} "
                    f"karta #{klic.client_card_id:<4} plocha {klic.unit} váha {klic.value}"
                )

        if sporne:
            self.stdout.write(self.style.ERROR(
                f"\nNEMAŽU - liší se Fakturovat/Odečíst proti klíči, který zůstává ({len(sporne)}):"))
            for klic, zustava in sporne:
                self.stdout.write(
                    f"   klíč #{klic.pk} ({klic.is_billed}/{klic.deduct_from_pool}) vs "
                    f"#{zustava.pk} ({zustava.is_billed}/{zustava.deduct_from_pool}) - {klic.service_item}"
                )

        if not zapsat:
            return

        with transaction.atomic():
            for klic in smazat:
                klic.delete()
            for klic, _stara, _nova in prepnout:
                klic.weight_source = AllocationKey.ZdrojVahy.PLOCHA
                klic.value = None
                # Vaha je ted soucet CELE Karty, takze vazba na jednu
                # konkretni Plochu uz jen mate (CALAMARI melo u odpadu
                # jediny klic, a ten visel na AB 1.07).
                klic.unit = None
                klic.save(update_fields=["weight_source", "value", "unit"])

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo: přepnuto {len(prepnout)}, smazáno {len(smazat)}. Přepočítej dotčená období."
        ))
