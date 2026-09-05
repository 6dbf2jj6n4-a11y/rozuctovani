"""Odkud brat vahu klice - misto priznaku "vytapena plocha" vyber ze tri.

Migrace 0102 zavedla dopocet vahy z vytapene plochy pro teplo NJ. Hned
se ukazalo, ze stejny problem je i na FM u sluzeb delenych podle m2:
vahy jsou tam RUCNE opsane metry a uz se rozesly - Vodama mela na
ostraze 170 misto 135 m2, TENAUR 941 misto 951, Chamrad 264 misto 263.
Nikdo si toho nevsiml, dokud se to neporovnalo s kartami.

Pole je proto nove vyber:
  "" (prazdne) - Hodnota zadana rucne, jako doposud
  "plocha"     - Cela plocha karty (ostraha, odvoz odpadu, uklid snehu)
  "vytapena"   - Vytapena plocha karty (teplo)

Daniel 2026-09-05 k tomu popsal, kam to smeruje: klice se maji doplnovat
automaticky ke kazde Plose, takze karta bude mit na jedne polozce klicu
vic. Ve stare aplikaci se to resilo "konsolidaci karty" - slucovanim do
jednoho souctoveho klice. Tady to neni potreba: billing/engine.py
zapocita dopoctenou plochu za kartu jen JEDNOU, at jich visi kolik chce.

Data: klice tepla NJ prejdou z priznaku na "vytapena".
"""
from django.db import migrations, models

VOLBY = [
    ("", "Hodnota zadaná ručně"),
    ("plocha", "Celá plocha karty (m²)"),
    ("vytapena", "Vytápěná plocha karty (m²)"),
]

NAPOVEDA = (
    "Místo pevné Hodnoty se váha spočítá z Ploch téhle Karty a "
    "přepočítá se sama při každém rozúčtování - nerozejde se, když "
    "se plocha přidá, ubere nebo se opraví výměra. „Celá plocha“ je "
    "pro služby placené podle velikosti pronajatého (ostraha, odvoz "
    "odpadu, úklid sněhu), „Vytápěná plocha“ pro teplo. Když má "
    "karta na jedné položce takových klíčů víc, plocha se započítá "
    "jen JEDNOU - klíče doplněné automaticky k plochám tak nemůžou "
    "nic zdvojit."
)


def prevest(apps, schema_editor):
    apps.get_model("core", "AllocationKey").objects.filter(
        weight_from_heated_area=True).update(weight_source="vytapena")


def zpet(apps, schema_editor):
    apps.get_model("core", "AllocationKey").objects.filter(
        weight_source="vytapena").update(weight_from_heated_area=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0102_klic_vaha_z_vytapene_plochy"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationkey",
            name="weight_source",
            field=models.CharField(
                blank=True, choices=VOLBY, default="", help_text=NAPOVEDA,
                max_length=20, verbose_name="Odkud brát váhu",
            ),
        ),
        migrations.RunPython(prevest, zpet),
        migrations.RemoveField(model_name="allocationkey", name="weight_from_heated_area"),
    ]
