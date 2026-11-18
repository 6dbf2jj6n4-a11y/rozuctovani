# Prepinac "Kladne ztraty si nechava pronajimatel" se presouva z globalniho
# Nastaveni rozuctovani na Tridu - Daniel 2026-11-18: u elektriny ne, u vody
# ano. Hodnota globalniho prepinace se prenese na vsechny Tridy, model
# NastaveniRozuctovani (mel jen tohle pole) se rusi.
# Psano rucne - makemigrations tu nabaluje nesouvisejici zmeny.

from django.db import migrations, models


def prenest(apps, schema_editor):
    Nastaveni = apps.get_model("core", "NastaveniRozuctovani")
    Trida = apps.get_model("core", "InvoiceClassColor")
    zaznam = Nastaveni.objects.first()
    if zaznam is not None and zaznam.kladne_ztraty_pronajimateli:
        Trida.objects.update(kladne_ztraty_pronajimateli=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0122_odberne_misto_dodavatel"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="kladne_ztraty_pronajimateli",
            field=models.BooleanField(
                default=False,
                help_text="Kladná ztráta = naše podružná měřidla naměřila VÍC, než fakturoval dodavatel. Vypnuto (výchozí): rozdělí se celá faktura mezi naměřené podíly, cena za jednotku klesne a rozdíl je bonusem nájemců. Zapnuto: nájemce platí své naměřené jednotky × cenu z faktury (částka ÷ fakturované množství) a přebytek zůstává pronajímateli jako výnos. Záporných ztrát (naměřili jsme míň) se netýká.",
                verbose_name="Kladné ztráty si nechává pronajímatel",
            ),
        ),
        migrations.RunPython(prenest, migrations.RunPython.noop),
        migrations.DeleteModel(name="NastaveniRozuctovani"),
    ]
