"""Vytapeny prostor a jeho vytapena plocha.

Teplo v NJ se dnes deli podle poctu radiatoru, coz nebere ohled na
velikost mistnosti. Daniel 2026-09-05: "podle mne neni uplne spravne
rozpocitavat podle poctu radiatoru, spravedlivejsi by bylo dle m2."

Ukazalo se, ze z Ucelu prostoru to odvodit nejde: v NJ jsou vytapene
i sklady v budove AB (Aktiv Novostav ma 144 m2 vytapenych skladu),
kdezto plechovy sklad vedle ne, a naopak kancelar AB 1.15 vytapena
neni. Priznak proto patri primo na Prostor.

Vytapena plocha se vyplnuje jen tam, kde se lisi od celkove vymery
(hala s temperovanou dilnou); prazdne znamena "topi se v celem
prostoru" - viz Unit.vytapena_plocha.

Data: predvyplneno pro NJ podle toho, co Daniel potvrdil - topi se
v budove AB krome AB 1.15, AB 1.17 a AB 1.18. Ostatni arealy zustavaji
vypnute, tam se to zatim neresi.
"""
from django.db import migrations, models

NEVYTAPENE_AB = ("AB 1.15", "AB 1.17", "AB 1.18")


def predvyplnit(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    Unit.objects.filter(
        site__name="NJ", name__startswith="AB ",
    ).exclude(name__in=NEVYTAPENE_AB).update(is_heated=True)


def zpet(apps, schema_editor):
    """Priznaky zaniknou s poli."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0099_meridlo_mimo_odecty"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="is_heated",
            field=models.BooleanField(
                default=False, verbose_name="Vytápěný",
                help_text=(
                    "Topí se v tomhle prostoru? Podle vytápěné plochy se dá rozúčtovat "
                    "teplo - spravedlivěji než podle počtu radiátorů, který nebere "
                    "ohled na velikost. Účel prostoru na to nestačí: v NJ jsou "
                    "vytápěné i sklady v budově AB, kdežto plechový sklad vedle ne."
                ),
            ),
        ),
        migrations.AddField(
            model_name="unit",
            name="heated_area_m2",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                verbose_name="Vytápěná plocha (m²)",
                help_text=(
                    "Vyplň jen když se vytápěná část liší od celkové výměry - třeba "
                    "hala, kde se temperuje jen dílna. Prázdné znamená, že se topí "
                    "v celém prostoru."
                ),
            ),
        ),
        migrations.RunPython(predvyplnit, zpet),
    ]
