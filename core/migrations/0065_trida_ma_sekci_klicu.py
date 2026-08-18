"""Prepinac "Vlastni sekce v Karte klienta a na Plose" na Tride.

Sekce Klicu (Karta klienta) a Vychozich sluzeb (Plocha) se od ted
generuji z Trid, misto aby byly napevno v kodu - viz core/admin.py
sekce_klicu()/sekce_sluzeb(). Prepinac urcuje, ktera Trida sekci dostane.

Najemne ji mit nema: v datech ho nic nepouziva (0 polozek, 0 meridel)
a najemne se zadava v sekci "Plochy a najemne" (CardUnit), ne klici.
Ostatni Tridy sekci maji, stejne jako pred touhle zmenou.
"""
from django.db import migrations, models


def vypnout_u_najemneho(apps, schema_editor):
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    InvoiceClassColor.objects.filter(invoice_class="najemne").update(ma_sekci_klicu=False)


def zapnout_vsem(apps, schema_editor):
    InvoiceClassColor = apps.get_model("core", "InvoiceClassColor")
    InvoiceClassColor.objects.update(ma_sekci_klicu=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0064_ceske_kody_trid"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceclasscolor",
            name="ma_sekci_klicu",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Zapnuto: Třída má v Kartě klienta vlastní sekci Klíčů a na Ploše "
                    "sekci Výchozích služeb. Vypni u Tříd, které se nerozúčtovávají "
                    "klíči - typicky Nájemné, to se zadává v sekci Plochy a nájemné."
                ),
                verbose_name="Vlastní sekce v Kartě klienta a na Ploše",
            ),
        ),
        migrations.RunPython(vypnout_u_najemneho, zapnout_vsem),
    ]
