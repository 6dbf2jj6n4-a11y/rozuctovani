"""Meridlo, ktere spravce nezadava.

T_SPOLECNA (pocet osob) a T_INDIVIDUALNI (pocet radiatoru) v NJ nesou
dohodnuta cisla, ne fyzicky odecet - spravci se v Zadavani odectu jen
pletla a hlasila se jako chybejici. Daniel 2026-09-05 se ptal, jestli je
muze oznacit jako Virtualni, aby zmizela. Nemuze: virtualni meridlo bez
Vzorce nikdy zadnou spotrebu nevrati (viz
billing/engine._meter_provides_consumption), takze by se rozpadlo deleni
tepla v NJ - na tech dvou meridlech visi 17 a 18 Klicu.

Nove je na to samostatny priznak, ktery se tyka VYHRADNE obrazovky
odectu. Vypocet, odecty i sestavy zustavaji beze zmeny; hodnota se dal
meni v administraci.

Data: zapnuto prave u T_SPOLECNA a T_INDIVIDUALNI v NJ.
"""
from django.db import migrations, models

NAPOVEDA = (
    "Schová měřidlo na obrazovce Zadávání odečtů - správce ho neuvidí "
    "a nebude ho hlásit jako chybějící. Pro měřidla, jejichž hodnota "
    "není fyzický odečet, ale dohodnuté číslo, které se skoro nemění "
    "(T_SPOLECNA = počet osob, T_INDIVIDUALNI = počet radiátorů). "
    "Do výpočtu to nijak nezasahuje: odečty měřidlo dál má a mění se "
    "v administraci. NEPLEŤ si to s „Virtuální“ - to měřidlo z výpočtu "
    "vyřadí, protože virtuální měřidlo bez Vzorce nikdy žádnou "
    "spotřebu nevrátí."
)


def zapnout(apps, schema_editor):
    apps.get_model("core", "Meter").objects.filter(
        site__name="NJ", code__in=("T_SPOLECNA", "T_INDIVIDUALNI"),
    ).update(skip_manual_reading=True)


def zpet(apps, schema_editor):
    """Priznak zanikne s polem."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0098_jak_se_zadava_naklad"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="skip_manual_reading",
            field=models.BooleanField(
                default=False, help_text=NAPOVEDA,
                verbose_name="Nezadává se v Odečtech",
            ),
        ),
        migrations.RunPython(zapnout, zpet),
    ]
