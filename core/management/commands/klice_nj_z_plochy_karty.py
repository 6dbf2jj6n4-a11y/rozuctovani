"""
Srazkove vody NJ: vaha se bere z Plochy Karty, ne z rucniho cisla.

Daniel 2026-09-16 porovnal klice vody v NJ se starou aplikaci. U 10 ze 13
karet sedely rucne zadane vymery na Plochy karty presne - ale tam, kde se
plochy prehazovaly mezi najemci, klic utekl:

  * CALAMARI #73 mel 223 + 10 + 15 = 248 m2 proti 261 m2 na karte.
    Kdyz si KJO vzalo AB 3.14 (13 m2), snizil se rucne hlavni klic
    a zaroven se plocha odebrala z karty - odectlo se to dvakrat.
  * INNEXUM (51) a ONE KLIMA (921) naopak sedi na karty a je to STARA
    aplikace, kdo ma zastarale 40 a 871.

Reseni je nedrzet stejne cislo na dvou mistech: klic dostane
weight_source = "plocha" (AllocationKey.ZdrojVahy.PLOCHA) a vahu si bere
primo z Karty. Engine zapocita odvozenou vahu jednou za Kartu a polozku,
takze ani vic klicu na jedne karte nic nezdvoji.

Zaroven se uklidi klice, ktere vznikly automaticky k jednotlivym Plocham:
  * u SRAZKOVYCH jsou po prepnuti zbytecne (vaha je uz soucet cele karty),
  * u VODY jsou primo spatne - vaha je POCET OSOB a pronajimatel nema tri
    lidi proto, ze ma tri mistnosti (CALAMARI melo 3 misto 1).

Prikaz je OPAKOVATELNY - druhe spusteni uz nema co menit.

Pouziti:
  python manage.py srazkove_nj_z_plochy_karty            # jen ukaze
  python manage.py srazkove_nj_z_plochy_karty --provest  # zapise
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AllocationKey, ServicePoolItem, Site


class Command(BaseCommand):
    help = "Srážkové vody NJ: váha z Plochy karty; úklid automatických klíčů k Plochám."

    def add_arguments(self, parser):
        parser.add_argument("--provest", action="store_true", help="Skutečně zapsat.")

    def handle(self, *args, **volby):
        zapsat = volby["provest"]
        site = Site.objects.filter(name="NJ").first()
        if site is None:
            raise CommandError("Areál NJ neexistuje.")
        srazkove = ServicePoolItem.objects.filter(site=site, name="srážkové vody NJ").first()
        voda = ServicePoolItem.objects.filter(site=site, name="hlavní odběr voda NJ").first()
        if srazkove is None or voda is None:
            raise CommandError("Položky „srážkové vody NJ“ / „hlavní odběr voda NJ“ neexistují.")

        if not zapsat:
            self.stdout.write(self.style.WARNING("NÁHLED - nic se nezapisuje, spusť s --provest.\n"))

        prepnuto, smazano_srazkove, smazano_voda = [], [], []

        # 1) srazkove: vaha z Plochy karty
        for klic in AllocationKey.objects.filter(
            service_item=srazkove
        ).select_related("client_card__client", "unit"):
            if klic.weight_source == AllocationKey.ZdrojVahy.PLOCHA and klic.value is None:
                continue
            prepnuto.append((klic, klic.value, klic.client_card.plocha_celkem))

        # 2) klice navazane na konkretni Plochu jsou po prepnuti nadbytecne -
        #    smazat je smi jen tehdy, kdyz na karte zbyde aspon jeden jiny.
        for polozka, kos in ((srazkove, smazano_srazkove), (voda, smazano_voda)):
            podle_karty = {}
            for klic in AllocationKey.objects.filter(
                service_item=polozka
            ).select_related("client_card__client", "unit"):
                podle_karty.setdefault(klic.client_card_id, []).append(klic)
            for klice in podle_karty.values():
                s_plochou = [k for k in klice if k.unit_id is not None]
                bez_plochy = [k for k in klice if k.unit_id is None]
                if s_plochou and bez_plochy:
                    kos.extend(s_plochou)

        smazane_id = {k.pk for k in smazano_srazkove}
        prepnuto = [z for z in prepnuto if z[0].pk not in smazane_id]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Srážkové vody NJ - váha z Plochy karty ({len(prepnuto)} klíčů):"))
        for klic, stara, nova in sorted(prepnuto, key=lambda z: str(z[0].client_card)):
            zmena = "" if stara == nova else self.style.WARNING("   <- MĚNÍ SE")
            self.stdout.write(
                f"   karta #{klic.client_card_id:<4} {str(klic.client_card)[:34]:34} "
                f"{stara} -> {nova} m²{zmena}"
            )

        for nazev, kos in (("srážkové vody NJ", smazano_srazkove), ("hlavní odběr voda NJ", smazano_voda)):
            if not kos:
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n{nazev} - smazat klíče navázané na jednotlivé Plochy ({len(kos)}):"))
            for klic in kos:
                self.stdout.write(
                    f"   klíč #{klic.pk:<5} karta #{klic.client_card_id:<4} "
                    f"{str(klic.client_card)[:30]:30} plocha {klic.unit} váha {klic.value}"
                )

        if not zapsat:
            return

        with transaction.atomic():
            for klic in smazano_srazkove + smazano_voda:
                klic.delete()
            for klic, _stara, _nova in prepnuto:
                klic.weight_source = AllocationKey.ZdrojVahy.PLOCHA
                klic.value = None
                klic.save(update_fields=["weight_source", "value"])

        self.stdout.write(self.style.SUCCESS(
            f"\nHotovo: přepnuto {len(prepnuto)} klíčů, smazáno "
            f"{len(smazano_srazkove) + len(smazano_voda)}. Přepočítej dotčená období."
        ))
