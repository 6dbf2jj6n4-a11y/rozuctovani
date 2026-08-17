from django.db import migrations, models


class Migration(migrations.Migration):
    """Polozka muze mit za obdobi VIC faktur od ruznych dodavatelu -
    elektrina FM prichazi od TEDOM EAN 240 i SZYPKA EAN, teplo NJ z pelet
    i ze zalozniho elektrokotle. Rozuctuje se jejich soucet jako jeden
    celek (fyzicky jde o jednu dodavku do stejne site, jen fakturovanou
    nadvakrat), takze musi padnout unikatni dvojice polozka+obdobi.

    Kazda faktura pritom muze mit vlastni cenu i jednotku - proto
    price_per_unit (prebiji Cenik) a unit_of_measure (podle nej se pozna,
    jestli jdou mnozstvi vubec secist; kg pelet a kWh elektriny ne).
    Viz konverzace s Danielem 2026-08-16."""

    dependencies = [
        ("core", "0059_supplypoint_cost_item"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="costentry",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="costentry",
            name="supplier",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="Dodavatel / zdroj",
                help_text=(
                    "Vyplň jen když má položka za období VÍC faktur od různých "
                    "dodavatelů (např. elektřina FM: TEDOM EAN 240 + SZYPKA EAN, "
                    "nebo teplo NJ: pelety + záložní elektrokotel). Náklady se "
                    "sečtou a rozúčtují jako jeden celek."
                ),
            ),
        ),
        migrations.AddField(
            model_name="costentry",
            name="price_per_unit",
            field=models.DecimalField(
                blank=True, null=True, max_digits=12, decimal_places=4,
                verbose_name="Cena za jednotku (Kč)",
                help_text=(
                    "Přebíjí Ceník. Vyplň, když má tenhle dodavatel jinou cenu než "
                    "ostatní - jinak nech prázdné a cena se vezme z Ceníku."
                ),
            ),
        ),
        migrations.AddField(
            model_name="costentry",
            name="unit_of_measure",
            field=models.CharField(
                blank=True, max_length=20, verbose_name="Jednotka",
                help_text=(
                    "kWh, m³, GJ, kg… Použije se jen k rozlišení, jestli jdou "
                    "množství z více faktur sečíst. Když se jednotky liší (pelety "
                    "v kg vs elektrokotel v kWh), rozúčtuje se pouze v Kč a "
                    "množství se nikde neukazuje."
                ),
            ),
        ),
    ]
