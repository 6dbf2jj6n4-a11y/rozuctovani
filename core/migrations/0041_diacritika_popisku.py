from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0040_move_weight_unit_label_to_meter'),
    ]

    operations = [
        migrations.AlterField(
            model_name='allocationkey',
            name='is_billed',
            field=models.BooleanField(default=True, help_text="Odpovídá sloupci 'FinTok' v původních Excel tabulkách klíčů. Pokud NE: částka se i tak započítá do výpočtu (spravedlivě snižuje podíl ostatních karet na sdíleném nákladu), ale klientovi se samostatně NEFAKTURUJE - typicky proto, že už ji má zahrnutou v paušální platbě (nájem + energie dohromady). Promítá se do BillingLine.is_billed a do klientského PDF vyúčtování (billing/statement_generator.py).", verbose_name='Fakturovat'),
        ),
        migrations.AlterField(
            model_name='allocationkey',
            name='valid_from',
            field=models.DateField(blank=True, help_text='Volitelné - typicky se platnost řeší na úrovni celé Karty klienta.', null=True, verbose_name='Platnost od'),
        ),
        migrations.AlterField(
            model_name='allocationkey',
            name='value',
            field=models.DecimalField(blank=True, decimal_places=4, help_text="Význam závisí na typu: u 'Pevná částka' jde o hotovou Kč částku/měsíc, u 'Dle výměry (m2)' jde o výměru v m2 (cena/m2/rok se bere z Ceníku položky pro dané období), u 'Podružné měřidlo' se použije jen pokud stejné měřidlo sdílí více karet - pak jde o váhu pro rozdělení jeho spotřeby mezi ně (u jedné karty na měřidlo se nepoužije, dostane celou spotřebu). U 'Podle váhy' jde o libovolné relativní číslo vyjadřující podíl na společném nákladu (m2, počet osob, počet kusů, radiátorů apod. - jednotka záleží na tom, jak položka danou spotřebu/náklad rozpočítává) - systém ho vždy normalizuje tak, aby součet všech karet dal dohromady 100 %, stačí tedy zadat správný POMĚR mezi kartami.", max_digits=12, null=True, verbose_name='Hodnota'),
        ),
        migrations.AlterField(
            model_name='billingline',
            name='is_billed',
            field=models.BooleanField(default=True, help_text='Snímek AllocationKey.is_billed v okamžiku výpočtu (viz billing/engine.py) - částka se počítala do rozpočtu vždy, ale pokud NE, klientovi se v PDF vyúčtování nepřipočítá do částky k úhradě (už ji má v paušálu).', verbose_name='Fakturováno klientovi'),
        ),
        migrations.AlterField(
            model_name='client',
            name='registry_court',
            field=models.CharField(blank=True, help_text="Např. 'Krajský soud v Ostravě' - lze dohledat/ověřit přes ARES podle IČO.", max_length=100, verbose_name='Rejstříkový soud'),
        ),
        migrations.AlterField(
            model_name='client',
            name='representative_name',
            field=models.CharField(blank=True, help_text="Např. 'Ing. Daniel DAVID' - u Pronajímatele se použije jako podpis ve Smlouvě.", max_length=200, verbose_name='Zástupce (jméno)'),
        ),
        migrations.AlterField(
            model_name='client',
            name='representative_role',
            field=models.CharField(blank=True, help_text="Např. 'jediný člen představenstva' nebo 'jednatel'.", max_length=200, verbose_name='Zástupce (funkce)'),
        ),
        migrations.AlterField(
            model_name='contract',
            name='representative_role',
            field=models.CharField(blank=True, help_text="Např. 'jednatel', 'na základě plné moci'.", max_length=100, verbose_name='Zastupuje (funkce)'),
        ),
        migrations.AlterField(
            model_name='meter',
            name='code',
            field=models.CharField(blank=True, help_text='Krátký kód pro odkazování ve vzorcích virtuálních měřičů (např. E_A1).', max_length=50, verbose_name='Kód'),
        ),
        migrations.AlterField(
            model_name='meter',
            name='formula',
            field=models.CharField(blank=True, help_text='Pouze pro virtuální měřidla, např. E_A1+E_AB1 (kódy jiných měřidel).', max_length=300, verbose_name='Vzorec'),
        ),
        migrations.AlterField(
            model_name='meter',
            name='is_virtual',
            field=models.BooleanField(default=False, help_text='Spotřeba se nepočítá z odečtů, ale ze vzorce odkazujícího na jiná měřidla (pole Vzorec).', verbose_name='Virtuální (vypočtené)'),
        ),
        migrations.AlterField(
            model_name='meter',
            name='reading_mode',
            field=models.CharField(choices=[('state', 'Stavy (kumulativní odečet, spotřeba = rozdíl mezi obdobími)'), ('consumption', 'Spotřeba za období (dodavatel hlásí rovnou spotřebu, ne stav)')], default='state', help_text='Většina měřidel hlásí kumulativní Stav (spotřeba se dopočítá jako rozdíl vůči minulému období). Pokud dodavatel hlásí rovnou Spotřebu za období (např. hlavní odběrné místo elektro), přepni na tento režim - pak stačí zadat odečet jen za aktuální období, hodnota se použije přímo.', max_length=20, verbose_name='Způsob zadávání odečtů'),
        ),
        migrations.AlterField(
            model_name='meter',
            name='weight_unit_label',
            field=models.CharField(blank=True, help_text="Krátký popis, co hodnota Klíče typu 'Podle váhy' napojeného na toto měřidlo znamená - např. 'm2', 'počet osob', 'počet radiátorů'. Typické pro virtuální 'zbytková' měřidla jako E_SPOL, kde se jejich spotřeba dělí mezi více karet vahou. Jen informativní (zobrazuje se v adminu a v Kartě klienta), na samotný výpočet nemá vliv.", max_length=100, verbose_name="Co je váhou (u klíčů 'Podle váhy' na tomto měřidle)"),
        ),
        migrations.AlterField(
            model_name='meterreading',
            name='value',
            field=models.DecimalField(decimal_places=3, help_text='Podle nastavení měřidla: buď kumulativní stav, nebo rovnou spotřeba za období.', max_digits=14, verbose_name='Stav / spotřeba'),
        ),
        migrations.AlterField(
            model_name='servicepoolitem',
            name='default_allocation_type',
            field=models.CharField(blank=True, choices=[('submeter', 'Podružné měřidlo (1:1)'), ('fixed_amount', 'Pevná částka'), ('weighted_count', 'Podle váhy'), ('area_price', 'Dle výměry (m²)')], help_text='Předvyplní se při založení nového klíče na kartě klienta pro tuto položku.', max_length=20, verbose_name='Výchozí typ rozpočtu'),
        ),
        migrations.AlterField(
            model_name='servicepoolitem',
            name='default_amount_czk',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Použije se při výpočtu rozúčtování pro období, pro které není zadaný žádný Náklad za období (CostEntry) - typicky pro služby s neměnnou paušální cenou (ostraha, internet...), aby se nemusela částka zadávat každý měsíc ručně. Pokud je pro dané období CostEntry zadaný, má vždy přednost před touto výchozí částkou.', max_digits=12, null=True, verbose_name='Výchozí měsíční částka (Kč)'),
        ),
        migrations.AlterField(
            model_name='site',
            name='name',
            field=models.CharField(max_length=200, verbose_name='Název'),
        ),
    ]
