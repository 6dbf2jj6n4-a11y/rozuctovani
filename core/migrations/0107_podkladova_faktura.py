"""Podkladove faktury - vazba polozky zasobniku a obdobi na prijatou
fakturu dodavatele v ABRA Flexi, aby ji klientsky portal mohl nabidnout
ke stazeni. Viz core.models.PodkladovaFaktura, Daniel 2026-09-25."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0106_spolecna_plocha"),
    ]

    operations = [
        migrations.CreateModel(
            name="PodkladovaFaktura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("flexi_id", models.PositiveIntegerField(verbose_name="ID faktury v ABRA")),
                ("kod", models.CharField(max_length=40, verbose_name="Číslo dokladu")),
                ("dodavatel", models.CharField(blank=True, max_length=200, verbose_name="Dodavatel")),
                ("popis", models.CharField(blank=True, max_length=200, verbose_name="Popis")),
                ("priloha_id", models.PositiveIntegerField(blank=True, null=True, verbose_name="ID přílohy v ABRA")),
                ("nazev_souboru", models.CharField(blank=True, max_length=255, verbose_name="Soubor")),
                ("nacteno", models.DateTimeField(auto_now=True, verbose_name="Načteno z ABRA")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="podkladove_faktury", to="core.period", verbose_name="Období")),
                ("service_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="podkladove_faktury", to="core.servicepoolitem", verbose_name="Položka zásobníku")),
            ],
            options={
                "verbose_name": "Podkladová faktura",
                "verbose_name_plural": "Podkladové faktury",
                "ordering": ["period__year", "period__month", "service_item__name", "kod"],
            },
        ),
        migrations.AddConstraint(
            model_name="podkladovafaktura",
            constraint=models.UniqueConstraint(fields=("service_item", "period", "flexi_id"), name="podkladova_faktura_jednou"),
        ),
    ]
