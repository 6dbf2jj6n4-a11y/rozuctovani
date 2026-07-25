from django.db import migrations, models

FM_LINES = [
    "Pronajímatel je výhradním vlastníkem nemovitostí zapsaných v katastru nemovitostí vedeném Katastrálním úřadem pro Moravskoslezský Kraj, Katastrální pracoviště Frýdek – Místek, na LV č. 2660 pro okres Frýdek – Místek, obec Frýdek – Místek a k. ú. Místek, a to:",
    "pozemku parc. č. 1914/1, druh pozemku ostatní plocha, způsob využití neplodná půda o výměře 2 m2,",
    "pozemku parc. č. 1932, druh pozemku zastavěná plocha a nádvoří, o výměře 218 m2,",
    "pozemku parc. č. 1933/1, druh pozemku zastavěná plocha a nádvoří, o výměře 14.749 m2,",
    "pozemku parc. č. 1935, druh pozemku zastavěná plocha a nádvoří, o výměře 64 m2,",
    "pozemku parc. č. 1942/4, druh pozemku ostatní plocha, způsob využití jiná plocha, o výměře 428 m2,",
    "pozemku parc. č. 3051/2, druh pozemku ostatní plocha, způsob využití ostatní komunikace, o výměře 359 m2,",
    "budovy č. p. 838, způsob využití bydlení, umístěné na shora uvedeném pozemku parc. č. 1932,",
    "budovy č. p. 839, způsob využití průmyslový objekt, umístěné na shora uvedeném pozemku parc. č. 1933/1,",
    "budovy č. p. 840, způsob využití jiná stavba, umístěné na shora uvedeném pozemku parc. č. 1935",
]

NJ_LINES = [
    "Pronajímatel je výhradním vlastníkem nemovitostí zapsaných v katastru nemovitostí vedeném Katastrálním úřadem pro Moravskoslezský Kraj, Katastrální pracoviště Nový Jičín, na LV č. 937 pro okres Nový Jičín, obec Šenov a k. ú. Šenov u Nového Jičína, a to:",
    "pozemku parc. č. 677/1, druh pozemku ostatní plocha, způsob využití manipulační plocha, o výměře 6.993 m2,",
    "pozemku parc. č. 677/2, druh pozemku ostatní plocha, způsob využití manipulační plocha, o výměře 4.067 m2,",
    "pozemku parc. č. 677/3, druh pozemku ostatní plocha, způsob využití manipulační plocha, o výměře 176 m2,",
    "pozemku parc. č. 677/5, druh pozemku ostatní plocha, způsob využití manipulační plocha, o výměře 434 m2,",
    "budovy č. p. 561, způsob využití výroba, umístěné na pozemcích parc. č. 674/1 a 674/2 (LV 60000) v uvedeném k.ú.,",
    "budovy bez č. p., způsob využití jiná stavba, umístěné na pozemku parc. č. 675 (LV 60000) v uvedeném k.ú.,",
    "budovy bez č. p., způsob využití jiná stavba, umístěné na pozemku parc. č. 676 (LV 60000) v uvedeném k.ú.",
]


def populate_lease_subject_text(apps, schema_editor):
    """Naplni Vymezeni predmetu najmu pro areály FM a NJ, pokud existuji -
    text extrahovan primo ze dvou realnych podepsanych smluv (viz commit).
    Zamerne tise nic neudela, pokud areal s timto nazvem neexistuje - jde
    jen o pohodlny vychozi obsah, ne o povinny udaj."""
    Site = apps.get_model("core", "Site")
    for name, lines in (("FM", FM_LINES), ("NJ", NJ_LINES)):
        Site.objects.filter(name=name).update(lease_subject_text="\n".join(lines))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_client_insolvency_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="site",
            name="lease_subject_text",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Používá se při generování Smlouvy (core/contract_generator.py). "
                    "První řádek je úvodní věta (katastrální úřad, LV, obec, k.ú.), "
                    "každý další řádek je jeden pozemek/budova z výčtu."
                ),
                verbose_name="Vymezení předmětu nájmu (text čl. 1 Smlouvy)",
            ),
        ),
        migrations.RunPython(populate_lease_subject_text, noop),
    ]
