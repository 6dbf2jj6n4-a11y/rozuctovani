from django.db import migrations, models


class Migration(migrations.Migration):
    """Prepinac "odecitat pausaly z celkoveho nakladu" po Tridach
    (Nastavení -> Třídy). Default True = dosavadni chovani: pausaly se
    odectou a mezi ostatni se deli jen zbytek. Vypnuti vrati model, jaky
    mel Danieluv puvodni system - pausaly jdou navic a cely naklad se
    deli mezi ostatni. Viz konverzace 2026-08-16 (teplo FM: pausaly
    ukrajovaly 64 % nakladu, takze merene podily platily ~40 % toho,
    co bylo fakturovano v ABRA)."""

    dependencies = [
        ("core", "0060_costentry_vice_dodavatelu"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="deduct_fixed_from_pool",
            field=models.BooleanField(
                default=True,
                verbose_name="Odečítat paušály z celkového nákladu",
                help_text=(
                    "Zapnuto: paušály (Pevná částka / Dle výměry) se nejdřív odečtou "
                    "z nákladu a mezi ostatní se dělí jen zbytek - klienti s měřidlem "
                    "tak platí méně. Vypnuto: paušály jdou navíc a celý náklad se dělí "
                    "mezi ostatní, jako to dělal starý systém. Platí pro celou třídu; "
                    "jednotlivý klíč může odečítání vypnout i tak, zapnout ale ne."
                ),
            ),
        ),
        migrations.AlterModelOptions(
            name="invoiceclasscolor",
            options={
                "verbose_name": "Nastavení třídy",
                "verbose_name_plural": "Třídy (barvy a paušály)",
                "ordering": ["invoice_class"],
            },
        ),
    ]
