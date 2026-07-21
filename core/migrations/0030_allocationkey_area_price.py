from django.db import migrations, models


ALLOCATION_TYPE_CHOICES = [
    ("percent", "Procento"),
    ("area_ratio", "Podle výměry (m²)"),
    ("person_count", "Podle počtu osob"),
    ("equal_split", "Rovným dílem"),
    ("submeter", "Podružné měřidlo (1:1)"),
    ("fixed_amount", "Pevná částka"),
    ("weighted_count", "Podle váhy (počet jednotek)"),
    ("area_price", "Plocha × cena/m² (dynamicky)"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_contract_site"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                verbose_name="Výchozí typ rozpočtu",
                max_length=20,
                blank=True,
                choices=ALLOCATION_TYPE_CHOICES,
                help_text="Predvyplni se pri zalozeni noveho klice na karte klienta pro tuto polozku.",
            ),
        ),
        migrations.AlterField(
            model_name="allocationkey",
            name="allocation_type",
            field=models.CharField(
                verbose_name="Typ rozpočtu",
                max_length=20,
                choices=ALLOCATION_TYPE_CHOICES,
            ),
        ),
        migrations.AlterField(
            model_name="allocationkey",
            name="value",
            field=models.DecimalField(
                verbose_name="Hodnota",
                max_digits=12,
                decimal_places=4,
                null=True,
                blank=True,
                help_text=(
                    "Vyznam zavisi na typu: u 'Pevna castka' jde o hotovou Kc castku/mesic, "
                    "u 'Plocha x cena/m2' jde o vymeru v m2 (cena/m2/rok se bere z Ceniku "
                    "polozky pro dane obdobi), u ostatnich typu jde o vahu/procento."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="allocationkey",
            name="deduct_from_pool",
            field=models.BooleanField(
                verbose_name="Odečíst z celkového nákladu",
                default=True,
                help_text=(
                    "Jen pro typ 'Pevná částka' a 'Plocha × cena/m²'. Pokud ANO (výchozí): tato "
                    "částka se odečte od celkového nákladu položky a zbytek se rozpočítá ostatním "
                    "kartám podle jejich klíčů (klient reálně snižuje sdílený náklad, napr. mel jiz "
                    "vlastni smlouvu). Pokud NE: klient zaplatí částku samostatně/navíc a celkový "
                    "náklad se mezi ostatní karty rozpočítá beze změny (typicky pausál, ktery "
                    "nesouvisí se sdílenym meridlem - napr. teplo bez pripojeni na hlavni odber)."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="unitservice",
            name="allocation_type",
            field=models.CharField(
                verbose_name="Typ rozpočtu",
                max_length=20,
                choices=ALLOCATION_TYPE_CHOICES,
                default="submeter",
            ),
        ),
    ]
