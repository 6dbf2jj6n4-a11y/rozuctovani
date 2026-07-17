from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_servicepoolitem_default_allocation_type_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationkey",
            name="deduct_from_pool",
            field=models.BooleanField(
                verbose_name="Odečíst z celkového nákladu",
                default=True,
                help_text=(
                    "Jen pro typ 'Pevná částka'. Pokud ANO (výchozí): tato pevná částka se "
                    "odečte od celkového nákladu položky a zbytek se rozpočítá ostatním kartám "
                    "podle jejich klíčů (klient reálně snižuje sdílený náklad, napr. mel jiz "
                    "vlastni smlouvu). Pokud NE: klient zaplatí pevnou částku samostatně/navíc "
                    "a celkový náklad se mezi ostatní karty rozpočítá beze změny (typicky "
                    "pausál, ktery nesouvisí se sdílenym meridlem - napr. teplo bez pripojeni "
                    "na hlavni odber)."
                ),
            ),
        ),
    ]
