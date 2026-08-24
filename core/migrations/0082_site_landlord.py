import django.db.models.deletion
from django.db import migrations, models


def naplnit(apps, schema_editor):
    """Kazdemu arealu priradi pronajimatele podle toho, jak se to dosud
    resilo obchvatem: areal V koeficientu DPH patri dosavadnimu (jedinemu)
    pronajimateli - plátci DPH; areal MIMO koeficient patri nekomu jinemu
    a musi se doplnit rucne. Viz konverzace s Danielem 2026-08-24."""
    Site = apps.get_model("core", "Site")
    Client = apps.get_model("core", "Client")
    puvodni = Client.objects.filter(is_landlord=True).order_by("pk").first()
    if puvodni is None:
        return
    Site.objects.filter(in_vat_coefficient=True, landlord__isnull=True).update(landlord=puvodni)


class Migration(migrations.Migration):
    """Pronajimatel prestava byt globalni priznak a stava se vlastnosti
    AREALU - Daniel pronajima DV jako fyzicka osoba neplatce DPH, kdezto
    FM a NJ pronajima CALAMARI SE. Dosud se to obchazelo priznakem
    Site.in_vat_coefficient, ktery presne kopiroval, komu areal patri.
    Viz konverzace s Danielem 2026-08-24."""

    dependencies = [
        ("core", "0081_spolubydlici"),
    ]

    operations = [
        migrations.AddField(
            model_name="site",
            name="landlord",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_sites", to="core.client",
                verbose_name="Pronajímatel",
                limit_choices_to={"is_landlord": True},
                help_text=(
                    "Subjekt, který tenhle areál pronajímá - vystupuje jako "
                    "pronajímatel ve smlouvách, na kartách i ve fakturačních "
                    "podkladech. Podle něj se taky pozná, jestli se areál počítá do "
                    "koeficientu DPH (počítá se jen u plátce DPH)."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="client",
            name="is_landlord",
            field=models.BooleanField(
                default=False, verbose_name="Pronajímatel",
                help_text=(
                    "Klient, který sám pronajímá - vystupuje jako pronajímatel ve "
                    "smlouvách a na kartách. Pronajímatelů může být víc (jiný "
                    "subjekt pro jiný areál); který patří ke kterému areálu, se "
                    "nastavuje u Areálu polem „Pronajímatel“."
                ),
            ),
        ),
        migrations.RunPython(naplnit, migrations.RunPython.noop),
    ]
