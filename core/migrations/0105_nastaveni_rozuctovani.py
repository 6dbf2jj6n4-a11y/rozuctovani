"""Obecna nastaveni rozuctovani + prepinac kladnych ztrat.

Dosud se vzdy rozdelila cela faktura mezi namerene podily. Kdyz podmery
namerily VIC nez dodavatel, cena za jednotku tim klesla a rozdil dostali
najemci - klient si pak ale nedokaze cislo overit: na fakture vidi jednu
cenu za kWh a na vyuctovani jinou, nizsi.

Daniel 2026-09-16: klient vzdycky vidi svuj stav meridla a na pozadani
i nasi nakladovou fakturu, takze si umi spocitat, kolik ma platit.
Jedine, co z dokladu nezjisti, je hodnota ztrat. Pro kladne ztraty ma
proto byt volba, jestli jdou ve prospech klientu, nebo zustavaji
pronajimateli jako vynos.

Vychozi poloha je VYPNUTO, tedy dnesni chovani - zapnuti je vedome
rozhodnuti, protoze meni penize na fakturach najemcu.

Zapornych ztrat (namerili jsme min nez dodavatel, typicky voda a teplo)
se prepinac netyka.
"""
from django.db import migrations, models

NAPOVEDA = (
    "Kladná ztráta = naše podměry naměřily VÍC, než fakturoval "
    "dodavatel.\n"
    "Vypnuto (výchozí): rozdělí se celá faktura mezi naměřené podíly, "
    "takže cena za jednotku klesne a rozdíl je bonusem nájemců.\n"
    "Zapnuto: nájemce platí své naměřené jednotky × cenu z faktury "
    "(částka ÷ fakturované množství). Vybere se víc, než přišlo na "
    "faktuře, a přebytek zůstává pronajímateli jako výnos - vidíš ho "
    "v přehledu Náklad/Výnos.\n"
    "ZÁPORNÝCH ztrát (naměřili jsme míň, typicky voda a teplo) se "
    "přepínač netýká - ty nesou nájemci jako dosud."
)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0104_odecet_potvrzene_varovani"),
    ]

    operations = [
        migrations.CreateModel(
            name="NastaveniRozuctovani",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True,
                                        serialize=False, verbose_name="ID")),
                ("kladne_ztraty_pronajimateli", models.BooleanField(
                    default=False, help_text=NAPOVEDA,
                    verbose_name="Kladné ztráty si nechává pronajímatel")),
            ],
            options={
                "verbose_name": "Nastavení rozúčtování",
                "verbose_name_plural": "Nastavení rozúčtování",
            },
        ),
    ]
