from django.db import migrations, models


class Migration(migrations.Migration):
    """Sjednany pevny mesicni najem na Plose karty. Dosud slo zadat jen
    Cenu Kc/m2/rok a najem se z ni pocital - u dohody typu "za 6 kancelari
    platis X Kc mesicne" se tak musela sazba za m2 zpetne dopocitavat, aby
    vysla spravna castka. Viz konverzace s Danielem 2026-08-17."""

    dependencies = [
        ("core", "0078_planek_na_r2"),
    ]

    operations = [
        migrations.AddField(
            model_name="cardunit",
            name="monthly_rent_override",
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
                verbose_name="Sjednané nájemné (Kč/měsíc)",
                help_text=(
                    "Vyplň, když je s klientem sjednaná PEVNÁ měsíční částka a ne "
                    "sazba za m² - typicky u nájmu za několik kanceláří dohromady. "
                    "Přebíjí výpočet z Ceny Kč/m²/rok, takže ji nemusíš zpětně "
                    "dopočítávat. Nech prázdné, když se nájem počítá z výměry."
                ),
            ),
        ),
    ]
