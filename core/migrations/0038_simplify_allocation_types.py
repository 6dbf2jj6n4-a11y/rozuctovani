from django.db import migrations, models


ALLOCATION_TYPE_CHOICES = [
    ("submeter", "Podružné měřidlo (1:1)"),
    ("fixed_amount", "Pevná částka"),
    ("weighted_count", "Podle váhy"),
    ("area_price", "Dle výměry (m²)"),
]

VALUE_HELP_TEXT = (
    "Vyznam zavisi na typu: u 'Pevna castka' jde o hotovou Kc castku/mesic, "
    "u 'Dle vymery (m2)' jde o vymeru v m2 (cena/m2/rok se bere z Ceniku "
    "polozky pro dane obdobi), u 'Podruzne meridlo' se pouzije jen pokud "
    "stejne meridlo sdili vice karet - pak jde o vahu pro rozdeleni jeho "
    "spotreby mezi ne (u jedne karty na meridlo se nepouzije, dostane celou "
    "spotrebu). U 'Podle vahy' jde o libovolne relativni cislo vyjadrujici "
    "podil na spolecnem nakladu (m2, pocet osob, pocet kusu, radiatoru "
    "apod. - jednotka zalezi na tom, jak polozka danou spotrebu/naklad "
    "rozpocitava) - system ho vzdy normalizuje tak, aby soucet vsech karet "
    "dal dohromady 100 %, staci tedy zadat spravny POMER mezi kartami."
)

# Typy 'percent', 'area_ratio', 'equal_split' a 'person_count' se rusi -
# vypocetne uz byly identicke s 'weighted_count' (viz billing/engine.py
# _weighted_shares pred touto migraci), takze prevod je bezeztratovy,
# hodnota (vaha) zustava beze zmeny.
TYPES_TO_MERGE = ["percent", "area_ratio", "equal_split", "person_count"]


def merge_into_weighted_count(apps, schema_editor):
    AllocationKey = apps.get_model("core", "AllocationKey")
    AllocationKey.objects.filter(allocation_type__in=TYPES_TO_MERGE).update(
        allocation_type="weighted_count"
    )
    ServicePoolItem = apps.get_model("core", "ServicePoolItem")
    ServicePoolItem.objects.filter(default_allocation_type__in=TYPES_TO_MERGE).update(
        default_allocation_type="weighted_count"
    )
    UnitService = apps.get_model("core", "UnitService")
    UnitService.objects.filter(allocation_type__in=TYPES_TO_MERGE).update(
        allocation_type="weighted_count"
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_allocationkey_billingline_is_billed"),
    ]

    operations = [
        migrations.RunPython(merge_into_weighted_count, noop_reverse),
        migrations.AlterField(
            model_name="allocationkey",
            name="allocation_type",
            field=models.CharField(
                choices=ALLOCATION_TYPE_CHOICES, max_length=20, verbose_name="Typ rozpočtu"
            ),
        ),
        migrations.AlterField(
            model_name="allocationkey",
            name="value",
            field=models.DecimalField(
                blank=True, decimal_places=4, help_text=VALUE_HELP_TEXT,
                max_digits=12, null=True, verbose_name="Hodnota",
            ),
        ),
        migrations.AlterField(
            model_name="servicepoolitem",
            name="default_allocation_type",
            field=models.CharField(
                blank=True, choices=ALLOCATION_TYPE_CHOICES, max_length=20,
                help_text="Predvyplni se pri zalozeni noveho klice na karte klienta pro tuto polozku.",
                verbose_name="Výchozí typ rozpočtu",
            ),
        ),
        migrations.AlterField(
            model_name="unitservice",
            name="allocation_type",
            field=models.CharField(
                choices=ALLOCATION_TYPE_CHOICES, default="submeter", max_length=20,
                verbose_name="Typ rozpočtu",
            ),
        ),
    ]
