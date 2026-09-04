from decimal import Decimal

from django.contrib import admin, messages
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.db.models import Q
from django.contrib.auth.models import Group

admin.site.unregister(Group)
from django.contrib.auth.models import User as AuthUser

try:
    admin.site.unregister(AuthUser)
except admin.sites.NotRegistered:
    pass
from django import forms
from unfold.decorators import display
from unfold.widgets import UnfoldBooleanSwitchWidget
from . import pronajimatele, rizika
from .admin_mixins import ModelAdmin, TabularInline

from .models import (
    Client, ClientCard, Contract, Site, Unit, CardUnit, Floorplan,
    Meter, MeterReading, Period, InflationRate, SupplyPoint, InvoiceClassColor,
    ServicePoolItem, AllocationKey, PriceList, CostEntry, BillingLine, UnitService,
    CardOccupant, ReadingsClosure,
    normalizovat_telefon,
)

class _PeriodDefaultMarkerFilter(admin.SimpleListFilter):
    """Neviditelny "filtr" bez skutecneho efektu - jediny ucel je, aby
    Django ChangeList rozpoznalo parametr '_pd' jako OCEKAVANY a vyjmulo
    ho z 'remaining_lookup_params' (SimpleListFilter.__init__ ho vzdy
    vytahne z params, bez ohledu na has_output()). Bez tohohle by se
    '_pd' zkousel pouzit jako qs.filter(_pd=...) - CostEntry/PriceList/
    MeterReading/BillingLine takove pole nemaji, takze by to spadlo na
    FieldError -> IncorrectLookupParameters -> po druhem pokusu (uz s
    '?e=1' v URL) na obecnou chybovou stranku Django adminu
    "admin/invalid_setup.html" ("Potíže s nainstalovanou databází...") -
    vypada to jako problem s DB, ale je to jen tohle. lookups() vraci
    prazdny seznam, takze has_output() je False a filtr se v bocnim
    panelu vubec nezobrazi. Viz DefaultToCurrentPeriodMixin."""
    title = "výchozí období"
    parameter_name = "_pd"

    def lookups(self, request, model_admin):
        return ()

    def queryset(self, request, queryset):
        return queryset


def colored_text(text, css_class):
    """Text obarveny podle Tridy - jen prida CSS tridu, konkretni barvy
    resi core.views.class_colors_css z Nastavení -> Barvy tříd (zvlast
    pro svetly a tmavy motiv). Pouziva se v seznamech, kde by barevne
    POZADI celeho radku bylo prilis - obarvi se jen kod/nazev.
    Viz konverzace s Danielem 2026-08-16."""
    from django.utils.html import format_html

    if text in (None, ""):
        return "—"
    if not css_class:
        return text
    return format_html('<span class="{}">{}</span>', css_class, text)


def colored_by_class(text, invoice_class):
    """Obarvi podle Tridy zasobniku (ServicePoolItem.InvoiceClass)."""
    return colored_text(text, InvoiceClassColor.css_class_for(invoice_class))


def colored_by_meter_type(text, meter_type):
    """Obarvi meridlo podle jeho Tridy - meridlo uz kod Tridy drzi primo
    (viz InvoiceClassColor)."""
    return colored_text(text, InvoiceClassColor.css_class_for_meter_type(meter_type))


def invoice_class_choice_field(db_field):
    """Formfield pro pole, ktera drzi kod Tridy (Meter.meter_type,
    SupplyPoint.meter_type, ServicePoolItem.invoice_class) - pole uz
    nemaji choices=, protoze zivy seznam Trid je v InvoiceClassColor
    (Nastavení -> Třídy), takze volby se sestavuji z aktualnich radku."""
    from django import forms
    from unfold.widgets import UnfoldAdminSelectWidget

    choices = InvoiceClassColor.choices()
    if db_field.blank:
        choices = [("", "---------")] + choices
    return forms.ChoiceField(
        choices=choices, required=not db_field.blank,
        label=db_field.verbose_name.capitalize() if db_field.verbose_name else None,
        help_text=db_field.help_text, widget=UnfoldAdminSelectWidget(choices=choices),
    )


class PodlePronajimatele:
    """Omezi seznam na data pronajimatele, se kterym uzivatel prave pracuje.

    Databaze je jedna a data obou pronajimatelu v ni lezi vedle sebe, ale
    uzivatel vidi vzdycky prave jednoho - viz core/pronajimatele.py.

    `cesta_k_arealu` je ORM cesta od tohohle modelu k core.Site (u Areálu
    samotneho "pk"). Zaznam, ktery se k zadnemu arealu priradit neda
    (napr. cerstve zalozeny klient jeste bez karty), se ukazuje VZDYCKY -
    schovat ho by znamenalo, ze ho Daniel nenajde a nedozvi se proc.

    Sdilene ciselniky (Obdobi, Tridy, Inflace) tenhle mixin nemaji, ty pod
    pronajimatele nepatri."""

    cesta_k_arealu = "site"
    zahrnout_neprirazene = True
    # Cesta pres zpetnou vazbu (napr. karta -> plochy) vraci radek
    # tolikrat, kolik ma navazanych zaznamu.
    potrebuje_distinct = False

    def dodatecne_q(self, request):
        """Co se ma videt navic bez ohledu na areal (viz ClientAdmin)."""
        return None

    def get_queryset(self, request):
        from django.db.models import Q

        from core import pronajimatele

        qs = super().get_queryset(request)
        podminka = Q(**{"%s__in" % self.cesta_k_arealu: pronajimatele.id_arealu(request)})
        if self.zahrnout_neprirazene:
            podminka |= Q(**{"%s__isnull" % self.cesta_k_arealu: True})
        navic = self.dodatecne_q(request)
        if navic is not None:
            podminka |= navic
        qs = qs.filter(podminka)
        return qs.distinct() if self.potrebuje_distinct else qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Nabidnout jen to, co je ve zvolenem kontextu videt.

        Plati pro kazde pole, jehoz cilovy model ma taky tenhle mixin -
        tedy Areal, ale i nadrazene Meridlo, Odberne misto nebo Polozku
        zasobniku. Bez toho by slo v kontextu DV zalozit meridlo pod
        meridlo z FM: ulozilo by se a hned zmizelo ze seznamu.

        Kdyz uz queryset nastavil nekdo pred nami (inline s vlastnim
        omezenim), nesahame na nej."""
        if "queryset" not in kwargs:
            spravce = admin.site._registry.get(db_field.related_model)
            if isinstance(spravce, PodlePronajimatele):
                kwargs["queryset"] = spravce.get_queryset(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class DefaultToCurrentPeriodMixin:
    """Pri prvnim otevreni seznamu (bez explicitne zvoleneho Obdobi)
    presmeruje na filtr podle AKTUALNIHO Obdobi (Period.current(), tj.
    dnesni kalendarni mesic) - stejna konvence plati na vsech custom
    admin sestavach s vyberem Obdobi. Drive se bralo nejnovejsi obdobi
    v DB, jenze od tlacitka "Generovat pro cely rok" jsou zalozene i
    budouci mesice. Marker '_pd' v querystringu odlisi
    "cerstve otevreni" od situace, kdy uzivatel filtr na Obdobi vedome
    zrusil (klikl na 'Vše' u filtru) - jinak by ho to porad vracelo zpet
    na nejnovejsi obdobi a nedalo by se videt vic obdobi najednou.

    DULEZITE: kazdy ModelAdmin pouzivajici tenhle mixin MUSI mit
    _PeriodDefaultMarkerFilter v list_filter, jinak viz FieldError
    popsany u _PeriodDefaultMarkerFilter vyse."""
    default_period_filter_param = "period__id__exact"

    def changelist_view(self, request, extra_context=None):
        if self.default_period_filter_param not in request.GET and "_pd" not in request.GET:
            latest = Period.current()
            if latest is not None:
                from django.shortcuts import redirect

                q = request.GET.copy()
                q[self.default_period_filter_param] = str(latest.pk)
                q["_pd"] = "1"
                return redirect(f"{request.path}?{q.urlencode()}")
        return super().changelist_view(request, extra_context)


class DuplicateModelAdminMixin:
    """Prida bulk akci "Kopírovat vybrané záznamy" - standardni Django
    trik pro klonovani instance (pk=None, _state.adding=True, save()).
    Overeno u Unit/Meter/Contract, ze zadny z nich nema unique/unique_together
    omezeni krome PK, takze takto vytvorena kopie projde bez IntegrityError.

    `prepare_duplicate(copy, original)`: hook pro upravu poli PRED ulozenim
    (napr. pridat "(kopie)" do nazvu, vynechat FileField) - `copy` uz ma
    pk=None, `original` jeste drzi puvodni pk.

    `after_duplicate(copy, original)`: hook PO ulozeni kopie (uz ma svuj
    novy pk) - pro dokopirovani souvisejicich radku (reverse FK), ktere
    field-by-field klon nezachyti (napr. UnitService u Unit)."""

    @admin.action(description="Kopírovat vybrané záznamy")
    def duplicate_selected(self, request, queryset):
        count = 0
        for original in queryset:
            copy = self.model.objects.get(pk=original.pk)
            copy.pk = None
            copy._state.adding = True
            self.prepare_duplicate(copy, original)
            copy.save()
            self.after_duplicate(copy, original)
            count += 1
        self.message_user(request, f"Zkopírováno {count} záznam(ů) - zkontroluj a uprav podle potřeby.", level=messages.SUCCESS)

    def prepare_duplicate(self, copy, original):
        """Vychozi chovani: nic dalsiho needit - cisty field-by-field klon."""

    def after_duplicate(self, copy, original):
        """Vychozi chovani: zadne souvisejici radky nekopirovat."""


class UnitInline(TabularInline):
    model = Unit
    extra = 0


@admin.register(Site)
class SiteAdmin(PodlePronajimatele, ModelAdmin):
    cesta_k_arealu = "pk"
    zahrnout_neprirazene = False
    list_display = ("name", "address", "landlord", "v_koeficientu_dph", "aktivnich_klientu")
    list_select_related = ("landlord",)
    list_filter = ("landlord",)
    search_fields = ("name",)
    autocomplete_fields = ("landlord",)
    inlines = [UnitInline]

    @display(description="V koeficientu DPH", boolean=True)
    def v_koeficientu_dph(self, obj):
        """Odvozeno z platcovstvi pronajimatele - u neplatce (fyzicka osoba)
        koeficient nedava smysl. Drive to drzel rucni priznak
        Site.in_vat_coefficient. Viz Daniel 2026-08-24."""
        return bool(obj.landlord_id and obj.landlord.vat_payer)

    def get_queryset(self, request):
        """Pocet RUZNYCH klientu, kteri maji v arealu aspon jednu aktivni
        Kartu. Vazba karta -> areal jde pres plochy (card_units__unit__site),
        stejne jako jinde v projektu (billing/engine.py, filtry v adminu) -
        karta muze mit ploch vic, proto distinct. Pocita se anotaci v
        dotazu, ne per radek, aby seznam Arealu nedelal dotaz navic za
        kazdy areal. Viz konverzace s Danielem 2026-08-16."""
        from django.db.models import Count

        return super().get_queryset(request).annotate(
            _aktivnich_klientu=Count(
                "units__card_units__card__client",
                filter=Q(units__card_units__card__is_active=True),
                distinct=True,
            )
        )

    @display(description="Aktivních klientů", ordering="_aktivnich_klientu")
    def aktivnich_klientu(self, obj):
        return obj._aktivnich_klientu


def _formset_se_stabilnim_prefixem(formset, invoice_class):
    """Da inline sekci vlastni, stabilni jmeno formulare odvozene od kodu
    Tridy (napr. "allocation_keys__elektro").

    Proc: kdyz je nad jednim modelem vic inline sekci, Django je rozlisuje
    JEN podle poradi - prvni dostane "allocation_keys", druha
    "allocation_keys-2" atd. (django/contrib/admin/options.py,
    _create_formsets). U sekci generovanych z Trid by staclo pridat Tridu
    v jinem okne a odeslana data by se ulozila do JINE sekce, nez do ktere
    je uzivatel zadal. S vlastnim jmenem na poradi nezalezi.

    Na jmenech formularu nezavisi zadny JS ani CSS - allocationkey_default_type.js
    i cardunit_autofill.js pracuji jen s koncovkami nazvu poli."""
    zaklad = formset.get_default_prefix()

    class FormSetSeStabilnimPrefixem(formset):
        @classmethod
        def get_default_prefix(cls):
            return f"{zaklad}__{invoice_class}"

    return FormSetSeStabilnimPrefixem


class UnitServiceInlineBase(TabularInline):
    model = UnitService
    extra = 0
    collapsible = True

    class Media:
        css = {"all": ("core/css/select_width_fix.css",)}

    def get_formset(self, request, obj=None, **kwargs):
        self.parent_obj = obj
        formset = super().get_formset(request, obj, **kwargs)
        return _formset_se_stabilnim_prefixem(formset, self.invoice_class)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            service_item__invoice_class=self.invoice_class
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        parent = getattr(self, "parent_obj", None)
        if db_field.name == "service_item":
            qs = pronajimatele.omez(
                ServicePoolItem.objects.filter(invoice_class=self.invoice_class),
                "site", request,
            )
            if parent is not None:
                qs = qs.filter(site=parent.site)
            kwargs["queryset"] = qs
        elif db_field.name == "meter":
            # Meridlo uz drzi primo kod Tridy, takze staci filtrovat na ni
            # (drive na to byl prevodni slovnik METER_TYPE_FOR_CLASS - po
            # sjednoceni Trid uz to byla identita).
            qs = pronajimatele.omez(
                Meter.objects.filter(meter_type=self.invoice_class), "site", request
            )
            if parent is not None:
                qs = qs.filter(site=parent.site)
            kwargs["queryset"] = qs

        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "meter" and hasattr(formfield.widget, "can_delete_related"):
            formfield.widget.can_delete_related = False
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
        return formfield


def sekce_sluzeb():
    """Sekce Vychozich sluzeb na Plose - jedna na kazdou Tridu se zapnutou
    volbou "Vlastni sekce" (Nastaveni -> Tridy). Viz sekce_klicu()."""
    return [
        type(
            f"UnitServiceInline_{trida.invoice_class}",
            (UnitServiceInlineBase,),
            {
                "invoice_class": trida.invoice_class,
                "verbose_name": f"Služba – {trida.label or trida.invoice_class}",
                "verbose_name_plural": trida.label or trida.invoice_class,
                "__module__": __name__,
            },
        )
        for trida in InvoiceClassColor.se_sekci()
    ]


@admin.register(Unit)
class UnitAdmin(PodlePronajimatele, DuplicateModelAdminMixin, ModelAdmin):
    cesta_k_arealu = "site"
    list_display = ("name", "site", "purpose", "area_m2", "unit_type", "druh_prostoru")
    list_select_related = ("site",)
    list_filter = ("site", "is_residential")
    search_fields = ("name",)
    actions = ["duplicate_selected"]

    @display(description="Druh", ordering="is_residential")
    def druh_prostoru(self, obj):
        """Slovem, ne zaskrtavatkem - 'Bytový/Nebytový' se v seznamu cte
        lip nez fajfka u sloupce 'Bytový prostor'."""
        return "Bytový" if obj.is_residential else "Nebytový"

    def get_inlines(self, request, obj=None):
        """Sekce se generuji z Trid (Nastaveni -> Tridy), ne napevno."""
        return sekce_sluzeb()

    def prepare_duplicate(self, copy, original):
        copy.name = f"{original.name} (kopie)"

    def after_duplicate(self, copy, original):
        """Zkopiruje i Vychozi sluzby plochy (UnitService) - jinak by
        kopie plochy byla bez nich, i kdyz se na formulari Plochy edituji
        primo jako inline (podobny princip jako ClientCard.create_exact_copy)."""
        for unit_service in original.unit_services.all():
            UnitService.objects.create(
                unit=copy,
                service_item=unit_service.service_item,
                allocation_type=unit_service.allocation_type,
                value=unit_service.value,
                meter=unit_service.meter,
            )

    def get_urls(self):
        from django.urls import path
        from django.http import JsonResponse

        def area_lookup(request, unit_id):
            # self.get_queryset drzi kontext pronajimatele (viz
            # PodlePronajimatele) - bez nej vracel doplnovac vymeru
            # prostoru i z cizich arealu. Daniel 2026-08-25.
            area = (
                self.get_queryset(request).filter(pk=unit_id)
                .values_list("area_m2", flat=True)
                .first()
            )
            return JsonResponse({"area": str(area) if area is not None else None})

        urls = super().get_urls()
        custom = [
            path(
                "area-lookup/<int:unit_id>/",
                self.admin_site.admin_view(area_lookup),
                name="core_unit_area_lookup",
            ),
        ]
        return custom + urls


class AllocationKeyInlineBase(TabularInline):
    model = AllocationKey
    extra = 0
    collapsible = True
    fields = ("service_item", "allocation_type", "value", "podil", "unit_price", "meter", "unit", "deduct_from_pool", "is_billed")
    readonly_fields = ("podil",)
    # Jen Plocha zustava naseptavacem - tech je na FM pres sto. Polozka
    # zasobniku a Meridlo jsou obycejny vyber schvalne: naseptavac chodi
    # pres vlastni endpoint, ktery filtr z teto sekce nevidi, takze
    # nabizel polozky VSECH Trid (Daniel 2026-09-08). Ve vyberu se
    # uplatni formfield_for_foreignkey nize, ktery omezi na Tridu sekce
    # i na areal Karty - polozek pak zbyde nanejvys deset.
    autocomplete_fields = ("unit",)

    @display(description="Podíl")
    def podil(self, obj):
        """Kolik z dane skupiny pripada na tenhle klic - tedy to, co se
        jinak da zjistit az ze sestavy Podil vah.

        Skupina je bud jedno MERIDLO (klice typu "Podle vahy na meridle"
        se stejnym meridlem), nebo u klicu bez meridla vsechny vazene
        klice te polozky. Cislo je podil UVNITR skupiny, ne podil na cene
        polozky - u meridla se totiz nejdriv vyrizne jeho namerena
        spotreba a teprve ta se timhle pomerem deli.

        Pocita se stejnym vzorcem jako engine (_weighted_shares): vaha
        krat pomer aktivnich dnu karty v aktualnim obdobi. Schvalne se
        NEPOUZIVA billing.weight_shares.get_weight_share_data - ta je
        presna i pro podil na cene, ale u karty s devíti polozkami trva
        pres pul minuty, coz do formulare nejde. Daniel 2026-08-26.
        """
        from decimal import Decimal

        from django.utils.html import format_html

        from core.models import Period

        if obj is None or not obj.pk or obj.allocation_type in ("fixed_amount", "area_price"):
            return "—"
        # Period.current() je dotaz do databaze - bez zapamatovani by se
        # volal na kazdy klic zvlast a pri latenci Railway to u karty
        # s dvaceti klici delalo pres sekundu.
        if not hasattr(self, "_pamet_obdobi"):
            self._pamet_obdobi = Period.current()
        obdobi = self._pamet_obdobi
        if obdobi is None:
            return "—"

        sourozenci = self._sourozenci(obj, obdobi)
        vahy = {}
        zacatek, konec = obdobi.date_range()
        dnu = Decimal(obdobi.days_in_period)
        for klic in sourozenci:
            aktivni = klic.client_card.active_days_in_period(zacatek, konec)
            if aktivni <= 0:
                continue
            vahy[klic.pk] = (klic.value or Decimal("0")) * (Decimal(aktivni) / dnu)
        celkem = sum(vahy.values())
        muj = vahy.get(obj.pk)
        if not celkem or muj is None:
            return "—"

        procenta = muj / celkem * 100
        kde = ("z měřidla %s" % obj.meter.code) if obj.meter_id else "ze skupiny bez měřidla"
        return format_html(
            '<span title="{} · {} karet ve skupině">{} %</span>',
            kde, len(vahy), ("%.1f" % procenta).replace(".", ","),
        )

    def _sourozenci(self, obj, obdobi):
        """Klice ve stejne skupine (stejna polozka + stejne meridlo).

        Nacita se po CELE POLOZCE najednou a rozdeli se v pameti podle
        meridla. Puvodne to byl dotaz na kazde meridlo zvlast, coz u karty
        s dvaceti klici delalo pres deset dotazu a pri latenci Railway
        pridavalo pres sekundu. Daniel 2026-08-26."""
        pamet = getattr(self, "_pamet_sourozencu", None)
        if pamet is None:
            pamet = self._pamet_sourozencu = {}
        if obj.service_item_id not in pamet:
            podle_meridla = {}
            qs = AllocationKey.objects.select_related("client_card").filter(
                service_item_id=obj.service_item_id,
            ).exclude(allocation_type__in=("fixed_amount", "area_price"))
            for klic in qs:
                if klic.is_valid_for_period(obdobi):
                    podle_meridla.setdefault(klic.meter_id, []).append(klic)
            pamet[obj.service_item_id] = podle_meridla
        return pamet[obj.service_item_id].get(obj.meter_id, [])

    class Media:
        css = {"all": ("core/css/select_width_fix.css",)}
        js = ("core/js/allocationkey_default_type.js",)

    def get_formset(self, request, obj=None, **kwargs):
        # Karta se musi zapamatovat DRIV, nez super() posklada pole -
        # formfield_for_foreignkey nize z ni bere areal a bez toho
        # nabizel Polozky a Meridla ze vsech arealu pronajimatele.
        # Viz Daniel 2026-09-08.
        self.parent_obj = obj
        formset = super().get_formset(request, obj, **kwargs)
        return _formset_se_stabilnim_prefixem(formset, self.invoice_class)

    def get_queryset(self, request):
        # Radi se podle Polozky zasobniku a v ramci ni podle Podruzneho
        # meridla - u karet s vic klici v jedne sekci se v nich jinak
        # spatne hleda. Klic BEZ meridla jde v ramci polozky prvni.
        #
        # nulls_first se pise vyslovne schvalne: Postgres radi prazdne
        # hodnoty pri vzestupnem razeni na KONEC, sqlite na zacatek -
        # bez toho by se poradi lisilo mezi testem a produkci.
        #
        # POZOR: uplne stejne telo metody ma UnitServiceInlineBase vyse,
        # tam ale meridlo nepatri. Daniel 2026-08-26.
        from django.db.models import F

        return super().get_queryset(request).filter(
            service_item__invoice_class=self.invoice_class
        ).order_by(
            "service_item__name", F("meter__code").asc(nulls_first=True), "pk"
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Nabidka se zuzuje na Tridu teto sekce a na areal Karty. Bez
        # toho se v sekci Voda nabizela i vodni polozka druheho arealu
        # a u Meridla dokonce vsechna meridla bez ohledu na Tridu.
        # Areal je znamy z parent_obj (viz get_formset vyse); u nove
        # zakladane Karty jeste plochy nema, tam se filtruje jen Tridou.
        # Viz Daniel 2026-09-08.
        parent = getattr(self, "parent_obj", None)
        # VSECHNY arealy Karty, ne jen prvni - Karta jich muze drzet vic
        # a pak by se polozky toho druheho vubec nenabidly (Daniel
        # 2026-09-08). U nove zakladane Karty plochy jeste nejsou, tam
        # se filtruje jen Tridou a pronajimatelem.
        arealy = list(parent.sites()) if parent is not None and parent.pk else []
        if db_field.name == "service_item":
            qs = pronajimatele.omez(
                ServicePoolItem.objects.filter(invoice_class=self.invoice_class),
                "site", request,
            )
            if arealy:
                qs = qs.filter(site__in=arealy)
            kwargs["queryset"] = qs.order_by("site__name", "name")
        elif db_field.name == "meter":
            qs = pronajimatele.omez(
                Meter.objects.filter(meter_type=self.invoice_class), "site", request
            )
            if arealy:
                qs = qs.filter(site__in=arealy)
            kwargs["queryset"] = qs.order_by("site__name", "code")
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("meter", "unit") and hasattr(formfield.widget, "can_delete_related"):
            formfield.widget.can_delete_related = False
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
        return formfield


def sekce_klicu():
    """Sekce Klicu v Karte klienta - jedna na kazdou Tridu se zapnutou
    volbou "Vlastni sekce" (Nastaveni -> Tridy).

    Drive to byly ctyri tridy napevno v kodu, takze nova Trida svou sekci
    nedostala a ty ctyri puvodni nesly smazat. Ted sekce sleduji data.
    Poradi je dane Meta.ordering na InvoiceClassColor (sort_order), na
    spravnost ukladani ale nema vliv - o to se stara stabilni prefix
    formulare, viz _formset_se_stabilnim_prefixem."""
    return [
        type(
            f"AllocationKeyInline_{trida.invoice_class}",
            (AllocationKeyInlineBase,),
            {
                "invoice_class": trida.invoice_class,
                "verbose_name": f"Klíč – {trida.label or trida.invoice_class}",
                "verbose_name_plural": trida.label or trida.invoice_class,
                # Stabilni CSS trida pro cilenou barvu pozadi sekce - podle
                # ni generuje pravidla
                # templates/admin/core/clientcard/invoiceclasscolor_style.html
                # z barev ulozenych u Tridy. Sama barvu nenese.
                "classes": (f"key-section-{trida.invoice_class}",),
                "__module__": __name__,
            },
        )
        for trida in InvoiceClassColor.se_sekci()
    ]


class CardOccupantInline(TabularInline):
    """Spolubydlici u Karty - viz docstring modelu CardOccupant.
    Nejcasteji u bytu, kde jsou najemci dva lide s ruznymi prijmenimi."""
    model = CardOccupant
    extra = 0
    fields = ("name", "note")
    verbose_name = "Spolubydlící"
    verbose_name_plural = "Spolubydlící"
    hide_title = True


class CardUnitInlineFormSet(forms.BaseInlineFormSet):
    """Karta se nesmi ulozit bez jedine Plochy.

    Model to hlida taky (ClientCard.clean), ale az u ulozene karty - pri
    zakladani Plochy jeste neexistuji, protoze vznikaji az po Karte.
    Tenhle formset zachyti obe situace: novou kartu, kde uzivatel zadnou
    plochu nevyplnil, i editaci, ve ktere smazal posledni.
    Viz Daniel 2026-08-25."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return  # necha promluvit konkretnejsi chyby jednotlivych radku
        zustavaji = [
            f.cleaned_data["unit"] for f in self.forms
            if getattr(f, "cleaned_data", None)
            and not f.cleaned_data.get("DELETE")
            and f.cleaned_data.get("unit")
        ]
        if not zustavaji:
            raise forms.ValidationError(
                "Karta musí mít aspoň jednu Plochu - vyber ji v sekci "
                "„Plochy a nájemné“."
            )
        # Jedna Karta = jeden areál - viz ClientCard.clean. Model to hlida
        # az u ulozene Karty, tenhle formular uz pri zadavani.
        arealy = {u.site_id: u.site for u in zustavaji}
        if len(arealy) > 1:
            raise forms.ValidationError(
                "Plochy jsou ze dvou areálů (%s). Jedna Karta patří vždy "
                "jednomu areálu - pronajímatel je vlastnost areálu, takže by "
                "smlouvu podepisovaly dvě různé osoby. Založ pro druhý areál "
                "samostatnou Kartu." % ", ".join(sorted(s.name for s in arealy.values()))
            )


class CardUnitInline(TabularInline):
    formset = CardUnitInlineFormSet
    model = CardUnit
    extra = 0
    fields = (
        "unit", "vymera_zasobnik", "area_m2_override", "rate_per_m2",
        "monthly_rent_override", "rocni_najem", "mesicni_najem", "rent_not_invoiced",
    )
    readonly_fields = ("vymera_zasobnik", "rocni_najem", "mesicni_najem")
    autocomplete_fields = ("unit",)
    verbose_name = "Plocha"
    verbose_name_plural = "Plochy a nájemné"

    class Media:
        js = ("core/js/cardunit_autofill.js",)

    def get_queryset(self, request):
        """Plochy podle abecedy - CardUnit zadne Meta.ordering nema, takze
        radky chodily v poradi, v jakem se zakladaly. Daniel 2026-08-26.

        POZOR na cisla: abecedne vyjde A10 pred A3, protoze se porovnavaji
        znaky, ne hodnoty. Na dnesnich datech se to tyka JEDINE karty
        (TENAUR, plochy A3 az A14); jinde maji nazvy v ramci karty stejny
        pocet cislic, takze poradi sedi. Prirozene razeni by chtelo vyraz
        specificky pro Postgres, coz by se nedalo overit na sqlite, na
        kterem bezi zkousky - proto zatim takhle."""
        return super().get_queryset(request).order_by("unit__name")

    def vymera_zasobnik(self, obj):
        if obj.unit and obj.unit.area_m2:
            return f"{obj.unit.area_m2} m²"
        return "—"
    vymera_zasobnik.short_description = "Výměra (zásobník)"

    def rocni_najem(self, obj):
        # Sjednana pevna castka ma prednost i tady - jinak by sloupec
        # ukazoval neco jineho nez skutecne uctovany najem.
        if obj.pk and obj.monthly_rent is not None:
            return _format_kc(obj.monthly_rent * 12)
        return _format_kc(None)
    rocni_najem.short_description = "Nájemné/rok"

    def mesicni_najem(self, obj):
        if obj.pk and obj.monthly_rent:
            return _format_kc(obj.monthly_rent)
        return _format_kc(None)
    mesicni_najem.short_description = "Nájemné/měsíc"


class ClientCardInlineForm(forms.ModelForm):
    class Meta:
        model = ClientCard
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        is_active = cleaned_data.get("is_active")
        if is_active and self.instance:
            self.instance.client = cleaned_data.get("client") or self.instance.client
            self.instance.is_active = True
            conflict = self.instance.active_card_conflict()
            if conflict:
                raise forms.ValidationError(
                    f"Klient už má aktivní kartu ve stejném areálu: {conflict.description}. "
                    "Nejprve deaktivujte stávající kartu."
                )
        return cleaned_data


class ClientCardInline(TabularInline):
    """Jen zobrazeni/editace existujicich Karet - pridavani nove Karty jde
    pres tlacitko "+ Přidat kartu" pod touto sekci (viz
    templates/admin/core/client/clientcard_inline_tabular.html), ktere
    vede na standardni pridavaci stranku Karty s klientem uz
    predvyplnenym. Inline pridavani je zamerne vypnute
    (has_add_permission=False) - prazdny radek pridany primo tady nema
    zadnou validaci povinnych udaju a driv na nej ani nesel kliknout
    (viz git historie - "Karta klienta s klíčem None")."""
    model = ClientCard
    form = ClientCardInlineForm
    extra = 0
    fields = ("description_link", "valid_from", "valid_to", "is_active", "note")
    readonly_fields = ("description_link",)
    can_delete = True
    verbose_name = "Karta"
    verbose_name_plural = "Karty klientů"
    template = "admin/core/client/clientcard_inline_tabular.html"
    # Unfold nad kazdym radkem inline vypisuje jeste nazev objektu
    # (ClientCard.__str__ = "Klient - Plocha - od M/RRRR"). Tady je to
    # zbytecne: klient je z te stranky zrejmy a popis karty je hned prvni
    # sloupec radku. Viz unfold/helpers/edit_inline/tabular_title.html.
    hide_title = True

    def has_add_permission(self, request, obj=None):
        return False

    def description_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if not obj.pk:
            return "(uložte klienta, pak půjde otevřít)"
        url = reverse("admin:core_clientcard_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.description or "—")
    description_link.short_description = "Popis karty"


class ContractInline(TabularInline):
    """Jen zobrazeni/editace existujicich Smluv - pridavani nove Smlouvy
    jde pres tlacitko "+ Přidat smlouvu" pod touto sekci (viz
    templates/admin/core/client/contract_inline_tabular.html), ktere
    vede na standardni pridavaci stranku Smlouvy s klientem uz
    predvyplnenym a vynucenymi povinnymi udaji (cislo, platnost od,
    vypovedni lhuta - viz ContractAdminForm). Inline pridavani je
    zamerne vypnute (has_add_permission=False)."""
    model = Contract
    extra = 0
    fields = ("number", "site", "valid_from", "signed_on", "deposit_czk", "deposit_paid", "has_inflation_clause")
    autocomplete_fields = ("site",)
    show_change_link = True
    template = "admin/core/client/contract_inline_tabular.html"

    verbose_name = "Smlouva"
    verbose_name_plural = "Smlouvy"

    def has_add_permission(self, request, obj=None):
        return False


class SiteFilter(admin.SimpleListFilter):
    title = "Areál"
    parameter_name = "site"

    def lookups(self, request, model_admin):
        return [(s.id, s.name) for s in pronajimatele.arealy(request)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                cards__card_units__unit__site_id=self.value()
            ).distinct()
        return queryset


class ClientCardSiteFilter(admin.SimpleListFilter):
    """Filtr Karet klientu podle arealu.

    Karta neni na areal navazana primo - vede k nemu pres Plochy karty
    (CardUnit -> Unit -> Site), stejne jako to dela SiteFilter u Klienta.
    Karta s plochami ve VIC arealech se proto zobrazi u kazdeho z nich;
    distinct() zajisti, ze se v seznamu neobjevi vickrat. Viz konverzace
    s Danielem 2026-08-19."""
    title = "Areál"
    parameter_name = "site"

    def lookups(self, request, model_admin):
        return [(s.id, s.name) for s in pronajimatele.arealy(request)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(card_units__unit__site_id=self.value()).distinct()
        return queryset


class ActiveClientFilter(admin.SimpleListFilter):
    """Vychozi zobrazeni jen aktivnich klientu - "Vse"/"Neaktivni" musi
    uzivatel vybrat sam. Na rozdil od beznych list_filter na is_active,
    kde je vychozi stav "Vse", tady je vychozi stav "Aktivni"."""
    title = "Aktivní"
    parameter_name = "is_active"

    def lookups(self, request, model_admin):
        return (
            ("1", "Aktivní"),
            ("0", "Neaktivní"),
            ("all", "Vše"),
        )

    def choices(self, changelist):
        value = self.value()
        for lookup, title in self.lookup_choices:
            selected = value == lookup or (value is None and lookup == "1")
            yield {
                "selected": selected,
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display": title,
            }

    def queryset(self, request, queryset):
        value = self.value()
        if value == "0":
            return queryset.filter(is_active=False)
        if value == "all":
            return queryset
        return queryset.filter(is_active=True)


# Predvolby pro combo u telefonu klienta. Zamerne kratky seznam - v praxi
# jsou to ceska a slovenska cisla; posledni volba nechava pole jako holy
# text pro cokoliv jineho (zahranici, klapka, dve cisla v jednom poli),
# aby se takovy zapis neprepisoval na nesmysl. Popisky jsou kratke -
# combo je uzke, aby nezabiralo misto cislu.
TELEFON_PREDVOLBY = [
    ("+420", "+420"),
    ("+421", "+421"),
    ("", "jiné"),
]


class TelefonWidget(forms.MultiWidget):
    """Predvolba jako rozbalovaci seznam + samotne cislo vedle.

    Vlastni sablona je nutna - vychozi MultiWidget da obe pole pod sebe."""

    template_name = "core/widgets/telefon.html"

    def __init__(self, attrs=None):
        from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

        super().__init__(
            [
                UnfoldAdminSelectWidget(choices=TELEFON_PREDVOLBY),
                # Zadny placeholder: klient bez telefonu ma mit pole
                # uplne prazdne. Driv tu bylo "123 456 789", coz vypadalo
                # jako skutecne vyplnene cislo; nahrada "XXX XXX XXX" mela
                # ukazovat jen tvar, ale prazdne pole to porad nebylo.
                # Tvar cisla hlida normalizovat_telefon pri ulozeni,
                # napovidat ho v poli netreba. Daniel 2026-08-24.
                UnfoldAdminTextInputWidget(),
            ],
            attrs,
        )

    def get_context(self, name, value, attrs):
        """Odstrani Alpine vazbu, kterou Unfold pridava podle jmena pole.

        Unfold (templatetags/unfold.py, changeform_condition) navesi na
        widget x-model.fill="<jmeno pole>". MultiWidget ten atribut preda
        OBEMA castem, takze by predvolba i cislo visely na jedne promenne
        a prepisovaly by se navzajem - vyber +421 by prepsal i cislo.
        Unfold si to resi jen u svych vlastnich MultiWidgetu (datum a cas,
        castka), nas nezna. Vazbu tu nepotrebujeme: conditional_fields u
        klienta stoji na entity_type, ne na telefonu."""
        context = super().get_context(name, value, attrs)
        for podwidget in context["widget"]["subwidgets"]:
            podwidget["attrs"].pop("x-model.fill", None)
        return context

    def decompress(self, value):
        if not value:
            return ["+420", ""]
        text = str(value).strip()
        for kod, _ in TELEFON_PREDVOLBY:
            if kod and text.startswith(kod):
                return [kod, text[len(kod):].strip()]
        # Neznamy tvar - cely do textoveho pole a predvolba "jiny zapis",
        # aby ho ulozeni nechalo presne tak, jak je.
        return ["", text]


class TelefonField(forms.MultiValueField):
    """Slozi predvolbu a cislo zpet do jednoho retezce, ktery se uklada.

    Model zustava jedno textove pole (Client.contact_phone), takze vsechno,
    co telefon jen cte (sestavy, PDF, exporty), funguje beze zmeny."""

    widget = TelefonWidget

    def __init__(self, **kwargs):
        kwargs.pop("max_length", None)
        kwargs.pop("empty_value", None)
        super().__init__(
            fields=(
                forms.ChoiceField(choices=TELEFON_PREDVOLBY, required=False),
                forms.CharField(required=False),
            ),
            require_all_fields=False,
            **kwargs,
        )

    def compress(self, hodnoty):
        if not hodnoty:
            return ""
        predvolba, cislo = (hodnoty[0] or ""), (hodnoty[1] or "").strip()
        if not cislo:
            return ""
        if not predvolba:
            return cislo
        return normalizovat_telefon(f"{predvolba} {cislo}")


@admin.register(Client)
class ClientAdmin(PodlePronajimatele, ModelAdmin):
    # Klient patri pod pronajimatele pres svoje karty. Cerstve zalozeny
    # klient jeste zadnou kartu nema, takze ho zahrnout_neprirazene nechava
    # videt vsem - jinak by po ulozeni zmizel driv, nez by se stihla
    # zalozit karta.
    cesta_k_arealu = "cards__card_units__unit__site"
    potrebuje_distinct = True

    def dodatecne_q(self, request):
        """Zvoleneho pronajimatele je videt, i kdyz nema kartu.

        Je to taky klient a ma smysl mu opravit fakturacni udaje. Ostatni
        pronajimatele se ale nenabizeji - v kontextu DV neni co delat
        s CALAMARI SE, a pres tohle chodi i naseptavac u pole Pronajimatel
        u Arealu, takze by slo omylem priradit areal cizi osobe.
        Viz Daniel 2026-08-25."""
        from django.db.models import Q

        from core import pronajimatele

        zvoleny = pronajimatele.aktualni(request)
        return Q(pk=zvoleny.pk) if zvoleny else None
    list_display = (
        "name_display", "code", "ico", "vat_payer", "contact_email", "contact_phone", "is_active",
    )
    # E-mail a telefon jdou prepsat primo v seznamu (ulozi se tlacitkem
    # dole pod tabulkou) - na Danielovo prani, aby se kvuli oprave
    # kontaktu nemusel proklikavat do detailu kazdeho klienta.
    # Prvni sloupec (name_display) zustava odkazem do detailu, jinak by
    # Django list_editable odmitlo (admin.E124).
    list_editable = ("contact_email", "contact_phone")
    search_fields = ("name", "ico", "code")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Telefon se zadava jako predvolba (combo) + cislo - viz
        TelefonField. Plati i v seznamu klientu, kde je pole editovatelne."""
        if db_field.name == "contact_phone":
            return TelefonField(required=False, label=db_field.verbose_name.capitalize(),
                                help_text=db_field.help_text)
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    list_filter = (ActiveClientFilter, "entity_type", "is_landlord", SiteFilter, "insolvency_status", "vat_payer")
    fieldsets = (
        ("Základní údaje", {
            "fields": (("name", "code"), ("is_active", "is_landlord"))
        }),
        ("Sídlo", {
            "fields": (("street", "street_number"), ("zip_code", "city"))
        }),
        ("Identifikace", {
            "fields": (
                ("ico", "dic", "ares_button"), "vat_payer",
                ("entity_type", "registry_source"),
                ("registry_court", "registry_section", "registry_insert"),
                ("representative_name", "representative_role"),
                "insolvency_status",
            )
        }),
        ("Bankovní spojení", {
            "fields": (("bank_name", "bank_account", "bank_code"),)
        }),
        ("Kontakt", {
            "fields": (("contact_email", "contact_phone"),)
        }),
    )
    readonly_fields = ("ares_button", "insolvency_status")
    # Zastupce/funkce davaji smysl jen u pravnicke osoby (za fyzickou
    # osobu jedna vzdy ona sama) - u fyzicke osoby se skryji.
    # Zivnostnik (fyzicka osoba + zivnostensky rejstrik) nema soud, oddil
    # ani vlozku - to jsou udaje z obchodniho rejstriku. Skryvaji se, a pri
    # ulozeni se i vyprazdni (viz Client.save), aby v DB nezustavaly stare
    # hodnoty po prepnuti zdroje. Viz konverzace s Danielem 2026-08-19.
    # Nepodnikatelsky subjekt (soukroma osoba, SVJ, spolek) - z Identifikace
    # mu zustava jen IČO a Insolvencni rejstrik, zbytek nedava smysl.
    _PODNIKATEL = "entity_type != 'nepodnikatel'"
    _BEZ_REJSTRIKU = (
        "!(entity_type == 'fyzicka' && registry_source == 'zivnostensky')"
        " && entity_type != 'nepodnikatel'"
    )
    conditional_fields = {
        "dic": _PODNIKATEL,
        "vat_payer": _PODNIKATEL,
        "registry_source": _PODNIKATEL,
        "representative_name": "entity_type != 'fyzicka' && entity_type != 'nepodnikatel'",
        "representative_role": "entity_type != 'fyzicka' && entity_type != 'nepodnikatel'",
        "registry_court": _BEZ_REJSTRIKU,
        "registry_section": _BEZ_REJSTRIKU,
        "registry_insert": _BEZ_REJSTRIKU,
    }
    inlines = [ClientCardInline, ContractInline]
    actions = ["export_emaily"]

    # Barvy nazvu klienta v seznamu. Drzi se tady jako konstanty, protoze
    # je krome obarveni pouziva i vysvetlivka nad tabulkou
    # (list_before_template) - jinak by se snadno rozesly.
    BARVA_RIZIKO = "#dc2626"
    BARVA_PRONAJIMATEL = "#ca8a04"

    # Pruh nad tabulkou: tlacitko "Zkontrolovat rizika (ARES)" + vysvetlivky
    # barev. Unfold tuhle sablonu vklada JESTE PRED <form id="changelist-form">
    # (viz unfold/templates/admin/change_list.html), takze vlastni <form>
    # tlacitka se do hromadnych akci nezanori - na rozdil od Obdobi, kde
    # vnoreny formular odesilal hromadnou akci.
    list_before_template = "admin/core/client/nad_seznamem.html"

    def changelist_view(self, request, extra_context=None):
        """Preda vysvetlivce stejne barvy, jakymi se obarvuji nazvy."""
        extra_context = extra_context or {}
        extra_context["barva_riziko"] = self.BARVA_RIZIKO
        extra_context["barva_pronajimatel"] = self.BARVA_PRONAJIMATEL
        # Tlacitko kontroly rizik prepisuje udaje klientu - kdo nema pravo
        # menit, at ho ani nevidi (view samo si to hlida znovu).
        extra_context["muze_menit_klienty"] = self.has_change_permission(request)
        return super().changelist_view(request, extra_context)

    def _is_risky(self, obj):
        """Klient v likvidaci nebo se zaznamem (aktivnim ci drivejsim)
        v insolvencnim rejstriku - viz core/management/commands/zkontrolovat_rizika.py."""
        return "v likvidaci" in obj.name.lower() or obj.insolvency_status in (
            Client.InsolvencyStatus.ACTIVE, Client.InsolvencyStatus.HISTORICAL,
        )

    @admin.display(description="Název", ordering="name")
    def name_display(self, obj):
        from django.utils.html import format_html
        if self._is_risky(obj):
            return format_html(
                '<span style="color:{}; font-weight:600;">{}</span>', self.BARVA_RIZIKO, obj.name
            )
        if obj.is_landlord:
            return format_html(
                '<span style="color:{}; font-weight:600;">{}</span>', self.BARVA_PRONAJIMATEL, obj.name
            )
        return obj.name

    class Media:
        js = ("core/js/ares_lookup.js",)

    def ares_button(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<button type="button" onclick="aresLookup()" class="rx-btn rx-btn-primary">'
            'Načíst z ARES</button>'
            '<span id="ares-status" style="margin-left:8px; font-size:13px;"></span>'
        )
    ares_button.short_description = ""

    def get_urls(self):
        from django.urls import path
        from django.http import JsonResponse

        def ico_lookup(request):
            ico = request.GET.get("ico", "").strip()
            if not ico:
                return JsonResponse({"exists": False})
            qs = Client.objects.filter(ico=ico)
            exclude_id = request.GET.get("exclude_id", "").strip()
            if exclude_id.isdigit():
                qs = qs.exclude(pk=exclude_id)
            client = qs.first()
            if client:
                return JsonResponse({
                    "exists": True,
                    "name": client.name,
                    "url": f"/admin/core/client/{client.pk}/change/",
                })
            return JsonResponse({"exists": False})

        def dph_lookup(request):
            from core.dph_registry import lookup_vat_payer

            ico = request.GET.get("ico", "").strip()
            if not ico:
                return JsonResponse({"found": False})
            result = lookup_vat_payer(ico)
            if not result:
                return JsonResponse({"found": False})
            return JsonResponse({"found": True, **result})

        urls = super().get_urls()
        custom = [
            path("ico-lookup/", self.admin_site.admin_view(ico_lookup), name="core_client_ico_lookup"),
            path("dph-lookup/", self.admin_site.admin_view(dph_lookup), name="core_client_dph_lookup"),
            path(
                "report/kontakty/",
                self.admin_site.admin_view(self.report_kontakty_view),
                name="core_client_report_kontakty",
            ),
            path(
                "kontrola-rizik/",
                self.admin_site.admin_view(self.kontrola_rizik_view),
                name="core_client_kontrola_rizik",
            ),
        ]
        return custom + urls

    def kontrola_rizik_view(self, request):
        """Tlacitko nad seznamem Klientu - totez, co mesicni prikaz
        `python manage.py zkontrolovat_rizika`, jen s vysledkem na strance
        a s odkazy primo na dotcene klienty.

        Kontroluji se VSICHNI aktivni klienti s ICO, napric pronajimateli
        (stejne jako prikaz) - je to udrzbova akce, ne report, a nemelo by
        smysl ji poustet zvlast za kazdeho pronajimatele.

        Jen POST: kontrola prepisuje nazvy klientu a insolvency_status,
        takze se nesmi dat spustit pouhym otevrenim odkazu (nacteni
        z historie, predvybirani odkazu prohlizecem apod.).
        """
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import redirect, render

        if not self.has_change_permission(request):
            raise PermissionDenied

        if request.method != "POST":
            return redirect("admin:core_client_changelist")

        vysledek = rizika.zkontrolovat()
        context = {
            **self.admin_site.each_context(request),
            "title": "Kontrola rizik v ARES",
            "opts": self.model._meta,
            "je_neco_k_reseni": rizika.je_neco_k_reseni(vysledek),
            **vysledek,
        }
        return render(request, "admin/core/client/kontrola_rizik.html", context)

    def report_kontakty_view(self, request):
        """Report (Reporty v menu): jednoduchy seznam aktivnich klientu
        s kontaktnimi udaji, pro rychly prehled/export."""
        from django.shortcuts import render

        clients = pronajimatele.klienti(
            request, Client.objects.filter(is_active=True)
        ).order_by("name")
        context = {
            **self.admin_site.each_context(request),
            "title": "Seznam klientů s kontakty",
            "clients": clients,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/client/report_kontakty.html", context)

    @admin.action(description="Zobrazit e-maily vybraných klientů (pro BCC)")
    def export_emaily(self, request, queryset):
        from django.contrib import messages
        emaily = [c.contact_email for c in queryset if c.contact_email]
        if not emaily:
            self.message_user(request, "Vybraní klienti nemají vyplněný e-mail.", level=messages.WARNING)
            return
        self.message_user(
            request,
            "E-maily (zkopíruj a vlož do BCC): " + "; ".join(emaily),
            level=messages.SUCCESS,
        )


class ContractAdminForm(forms.ModelForm):
    # Widget se musi nastavit rucne: Unfold prepina BooleanField na prepinac
    # pres FORMFIELD_OVERRIDES, ktere se ale aplikuji jen na pole MODELU
    # (formfield_for_dbfield). Tohle je pole formulare (v modelu neexistuje,
    # uklada se jen jako valid_to=None v clean()), takze by jinak zustalo
    # obycejnym zaskrtavatkem a nesedelo by k prepinaci Inflacni dolozky.
    na_dobu_neurcitou = forms.BooleanField(
        label="Na dobu neurčitou", required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text="Zapnuto (výchozí) = pole 'Platnost do' se nepoužije a zůstane prázdné.",
    )

    class Meta:
        model = Contract
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["number"].required = True
        self.fields["valid_from"].required = True
        if not self.instance.pk or not self.instance.valid_to:
            self.fields["na_dobu_neurcitou"].initial = True

        # Vypovedni lhuta ma smysl jen u smlouvy na dobu neurcitou - na dobu
        # urcitou se vypovedet bez udani duvodu neda (cl. 7.2 pism. b) se
        # v takove smlouve negeneruje), takze je pole skryte (viz
        # conditional_fields) a nesmi byt povinne, jinak by slo formular
        # ulozit jen po vyplneni pole, ktere uzivatel nevidi. Pri odeslani
        # se stav bere z odeslanych dat, ne z instance - uzivatel mohl
        # prepinac prave prehodit.
        if self.is_bound:
            na_dobu_neurcitou = bool(self.data.get(self.add_prefix("na_dobu_neurcitou")))
        else:
            na_dobu_neurcitou = bool(self.fields["na_dobu_neurcitou"].initial)
        self.fields["notice_period_months"].required = na_dobu_neurcitou

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("na_dobu_neurcitou"):
            cleaned_data["valid_to"] = None
        else:
            cleaned_data["notice_period_months"] = None
        return cleaned_data


@admin.register(Contract)
class ContractAdmin(PodlePronajimatele, DuplicateModelAdminMixin, ModelAdmin):
    cesta_k_arealu = "site"
    form = ContractAdminForm
    list_display = ("client", "number", "valid_from", "valid_to", "deposit_paid", "has_inflation_clause")
    list_select_related = ("client",)
    list_filter = ("deposit_paid", "has_inflation_clause")
    search_fields = ("number", "client__name", "client__ico")
    autocomplete_fields = ("client", "site")
    actions = ["generate_document", "generovat_karty_inflace", "duplicate_selected"]

    def prepare_duplicate(self, copy, original):
        """Vygenerovany dokument (PDF/DOCX) se NEKOPIRUJE - patri k
        puvodni Smlouve, ne ke kopii (ta jeste zadny svuj dokument nema,
        dokud se pro ni znovu nespusti akce "Vygenerovat dokument")."""
        copy.number = f"{original.number} (kopie)" if original.number else ""
        copy.document = None

    def get_changeform_initial_data(self, request):
        """Pri zalozeni nove Smlouvy (tlacitko "+ Pridat smlouvu" na Klientovi,
        viz contract_inline_tabular.html) predvyplni:
        - zastupce a fakturacni e-mail z navazaneho Klienta - jsou to
          samostatna pole Smlouvy (mohou se od Klienta lisit), takze jde jen
          o initial hodnotu formulare, ne o kopii pri ulozeni;
        - datum podpisu = dnes, platnost od = 1. den nasledujiciho mesice,
          vypovedni lhuta = 3 mesice, inflacni dolozka zaskrtnuta a jeji
          navyseni od 1.1. nasledujiciho roku - bezne vychozi hodnoty
          noveho pronajmu;
        - kauci ve vysi jednoho najmu, pokud uz ma Klient aktivni Kartu
          s vyplnenym najemnym na Plochach (CardUnit.monthly_rent) - jinak
          se pole nechava prazdne k rucnimu doplneni."""
        from datetime import date

        initial = super().get_changeform_initial_data(request)
        client_id = initial.get("client")
        if client_id:
            client = Client.objects.filter(pk=client_id).first()
            if client:
                initial.setdefault("representative_name", client.representative_name)
                initial.setdefault("representative_role", client.representative_role)
                initial.setdefault("invoicing_email", client.contact_email)

                monthly_rent_total = sum(
                    (cu.monthly_rent or 0)
                    for card in client.cards.filter(is_active=True)
                    for cu in card.card_units.all()
                )
                if monthly_rent_total:
                    initial.setdefault("deposit_czk", monthly_rent_total)

        today = date.today()
        if today.month == 12:
            next_month_first = date(today.year + 1, 1, 1)
        else:
            next_month_first = date(today.year, today.month + 1, 1)

        initial.setdefault("signed_on", today)
        initial.setdefault("valid_from", next_month_first)
        initial.setdefault("notice_period_months", 3)
        initial.setdefault("has_inflation_clause", True)
        initial.setdefault("inflation_increase_from", date(today.year + 1, 1, 1))
        return initial

    conditional_fields = {
        "valid_to": "na_dobu_neurcitou == false",
        "notice_period_months": "na_dobu_neurcitou == true",
    }

    @admin.action(description="Vygenerovat nové karty s inflací")
    def generovat_karty_inflace(self, request, queryset):
        from datetime import datetime, timedelta
        from django.shortcuts import render

        if "apply" in request.POST:
            valid_from_str = request.POST.get("valid_from")
            rate = InflationRate.objects.filter(pk=request.POST.get("inflation_rate")).first()
            try:
                new_valid_from = datetime.strptime(valid_from_str, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                self.message_user(request, "Zadej platné datum platnosti nové karty.", level=messages.ERROR)
                return None
            if not rate:
                self.message_user(request, "Vyber míru inflace.", level=messages.ERROR)
                return None

            factor = Decimal("1") + rate.percent / Decimal("100")
            created = 0
            skipped = []
            for contract in queryset:
                if not contract.has_inflation_clause:
                    skipped.append(f"{contract} (#{contract.pk}): nemá inflační doložku")
                    continue
                if not contract.site_id:
                    skipped.append(f"{contract} (#{contract.pk}): chybí Areál na smlouvě")
                    continue
                candidates = [
                    c for c in ClientCard.objects.filter(client=contract.client, is_active=True)
                    if contract.site in c.sites()
                ]
                if len(candidates) != 1:
                    skipped.append(
                        f"{contract} (#{contract.pk}): nalezeno {len(candidates)} aktivních karet "
                        f"klienta v areálu {contract.site} (očekávána 1) - přeskočeno"
                    )
                    continue
                old_card = candidates[0]
                new_card = old_card.create_exact_copy(valid_from=new_valid_from, is_active=True)
                for cu in new_card.card_units.all():
                    if cu.rate_per_m2 is not None:
                        cu.rate_per_m2 = (cu.rate_per_m2 * factor).quantize(Decimal("0.01"))
                        cu.save(update_fields=["rate_per_m2"])
                old_card.valid_to = new_valid_from - timedelta(days=1)
                old_card.is_active = False
                old_card.save(update_fields=["valid_to", "is_active"])
                created += 1

            text = f"Vytvořeno {created} nových karet s navýšením nájemného o {rate.percent} %."
            if skipped:
                text += " Přeskočeno: " + " | ".join(skipped)
                self.message_user(request, text, level=messages.WARNING)
            else:
                self.message_user(request, text, level=messages.SUCCESS)
            return None

        context = {
            **self.admin_site.each_context(request),
            "title": "Vygenerovat nové karty s inflací",
            "contracts": queryset,
            "rates": InflationRate.objects.all(),
            "action_checkbox_name": "_selected_action",
            "opts": self.model._meta,
        }
        return render(request, "admin/core/contract/generovat_karty_inflace.html", context)

    @admin.action(description="Vygenerovat dokument smlouvy (.docx)")
    def generate_document(self, request, queryset):
        from io import BytesIO
        from django.core.files.base import ContentFile
        from core.contract_generator import contract_to_template_data, fill_contract_template

        generated, skipped = 0, []
        for contract in queryset:
            if not contract.site_id:
                skipped.append(f"{contract} (#{contract.pk}): chybí Areál")
                continue
            try:
                buf = BytesIO()
                fill_contract_template(contract_to_template_data(contract), buf)
            except Exception as exc:
                skipped.append(f"{contract}: {exc}")
                continue
            filename = f"smlouva_{contract.client.code or contract.client.pk}_{contract.pk}.docx"
            contract.document.save(filename, ContentFile(buf.getvalue()), save=True)
            generated += 1

        text = f"Vygenerováno {generated} dokumentů."
        if skipped:
            text += " Přeskočeno: " + " | ".join(skipped)
            self.message_user(request, text, level=messages.WARNING)
        else:
            self.message_user(request, text, level=messages.SUCCESS)

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path(
                "<int:contract_id>/generovat/",
                self.admin_site.admin_view(self.generate_and_download),
                name="core_contract_generovat",
            ),
        ]
        return custom + urls

    def generate_and_download(self, request, contract_id):
        from io import BytesIO
        from django.core.files.base import ContentFile
        from django.http import HttpResponse
        from django.shortcuts import redirect
        from core.contract_generator import contract_to_template_data, fill_contract_template

        # Objekt z URL musi projit stejnym filtrem jako seznam, jinak si
        # sel po prepnuti pronajimatele stahnout cizi smlouvu i s udaji
        # klienta. Daniel 2026-08-25.
        contract = self.get_queryset(request).filter(pk=contract_id).first()
        if contract is None:
            self.message_user(request, "Smlouva patří jinému pronajímateli.",
                              level=messages.ERROR)
            return redirect("admin:core_contract_changelist")
        if not contract.site_id:
            self.message_user(
                request,
                "Nejprve vyplň Areál - je potřeba pro záhlaví dokumentu.",
                level=messages.ERROR,
            )
            return redirect("admin:core_contract_change", contract.pk)
        buf = BytesIO()
        try:
            fill_contract_template(contract_to_template_data(contract), buf)
        except ValueError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return redirect("admin:core_contract_change", contract.pk)
        filename = f"smlouva_{contract.client.code or contract.client.pk}_{contract.pk}.docx"
        contract.document.save(filename, ContentFile(buf.getvalue()), save=True)

        response = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def generate_button(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if not obj.pk:
            return "Nejprve smlouvu uložte."
        url = reverse("admin:core_contract_generovat", args=[obj.pk])
        return format_html(
            '<a href="{}" class="rx-btn rx-btn-primary">'
            'Generovat smlouvu (.docx)</a>',
            url,
        )
    generate_button.short_description = ""

    readonly_fields = ("generate_button",)

    fieldsets = (
        ("Základní údaje", {
            "fields": (("client", "site", "number"), "signed_on")
        }),
        ("Platnost", {
            "fields": ("na_dobu_neurcitou", ("valid_from", "valid_to"), "notice_period_months")
        }),
        ("Kauce a pojištění", {
            "fields": (("deposit_czk", "deposit_paid"), "insurance_amount_czk")
        }),
        ("Inflační doložka", {
            "fields": (("has_inflation_clause", "inflation_increase_from"),)
        }),
        ("Fakturace a zastoupení", {
            "fields": ("invoicing_email", ("representative_name", "representative_role"))
        }),
        ("Dokument", {
            "fields": ("generate_button", "document")
        }),
        ("Poznámka", {
            "fields": ("note",)
        }),
    )


class ClientCardClientActiveFilter(admin.SimpleListFilter):
    """Client.is_active i ClientCard.is_active se v modelu jmenuji stejne
    ("Aktivní") - obycejny list_filter = ("client__is_active", "is_active")
    proto v adminu zobrazi DVA filtry se stejnym nazvem, bez rozliseni, ktery
    je za co (viz konverzace s Danielem)."""
    title = "Klient aktivní"
    parameter_name = "client_active"

    def lookups(self, request, model_admin):
        return (("1", "Ano"), ("0", "Ne"))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(client__is_active=True)
        if self.value() == "0":
            return queryset.filter(client__is_active=False)
        return queryset


class ClientCardActiveFilter(admin.SimpleListFilter):
    title = "Karta aktivní"
    parameter_name = "card_active"

    def lookups(self, request, model_admin):
        return (("1", "Ano"), ("0", "Ne"))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(is_active=True)
        if self.value() == "0":
            return queryset.filter(is_active=False)
        return queryset


@admin.register(ClientCard)
class ClientCardAdmin(PodlePronajimatele, ModelAdmin):
    # Unfoldova funkce warn_unsaved_form (zaplá globálně na ModelAdmin) rozbíjí
    # na této stránce tlačítko "Přidat další" u inline klíčů - vypínáme ji a
    # varování o neuložených změnách řešíme vlastním JS (warn_unsaved.js), který
    # "Přidat" nerozbíjí. Viz konverzace s Danielem.
    warn_unsaved_form = False
    cesta_k_arealu = "card_units__unit__site"
    potrebuje_distinct = True
    list_display = ("client", "description", "valid_from", "valid_to", "is_active")
    # Vygeneruje <style> pravidla pro barvy sekci Elektřina/Voda/Teplo/
    # Ostatní podle aktualnich hodnot InvoiceClassColor (Nastavení ->
    # Barvy tříd) - viz key-section-* tridy na
    # AllocationKey*Inline.classes vyse. Tohle je jediny kousek, ktery
    # NEJDE bez male dynamicke <style> sablony - barva je uzivatelsky
    # editovatelna hodnota z DB, takze ji neni jak predem "zabudovat"
    # do staticke Tailwind tridy (na rozdil od zbytku adminu, kde
    # stacily hotove Unfold/Tailwind tridy).
    change_form_before_template = "admin/core/clientcard/invoiceclasscolor_style.html"

    class Media:
        js = ("core/js/warn_unsaved.js",)
    list_select_related = ("client",)
    list_filter = (ClientCardClientActiveFilter, ClientCardActiveFilter, ClientCardSiteFilter)
    autocomplete_fields = ("client",)
    search_fields = ("client__name", "description")
    fieldsets = (
        ("Základní údaje", {
            "fields": (("client", "description"), ("valid_from", "valid_to"),
                       "contract", "is_active", "note")
        }),
        ("Čísla objednávek (na faktury)", {
            "fields": (("po_number_rent", "po_number_services"),)
        }),
        ("Karta nájemce (Příloha č. 1)", {
            # Datum podpisu a miniatura Karty na jednom radku - v jedne
            # n-tici je admin sazi vedle sebe, kazde zvlast pod sebe.
            # Daniel 2026-08-26.
            "fields": (("signed_on", "generate_card_button"), "document")
        }),
    )
    readonly_fields = ("generate_card_button",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """V poli Smlouva nabidnout jen smlouvy tohoto klienta.

        Bez toho by admin vypsal vsechny smlouvy v aplikaci. U prave
        zakladane Karty klient jeste znamy neni - tam zustanou smlouvy
        pronajimatele, se kterym uzivatel pracuje. Viz Daniel 2026-09-08."""
        if db_field.name == "contract":
            qs = pronajimatele.omez(Contract.objects.all(), "site", request)
            karta_id = (request.resolver_match.kwargs.get("object_id")
                        if request.resolver_match else None)
            if karta_id:
                karta = ClientCard.objects.filter(pk=karta_id).first()
                if karta is not None:
                    qs = qs.filter(client_id=karta.client_id)
            kwargs["queryset"] = qs.select_related("site").order_by("-valid_from")
            pole = super().formfield_for_foreignkey(db_field, request, **kwargs)
            # Contract.__str__ vraci prazdny retezec, takze by v nabidce
            # byly prazdne radky - popisek si tedy sestavime tady.
            pole.label_from_instance = lambda s: "č. {} ({}{})".format(
                s.number or "bez čísla",
                s.site.name if s.site_id else "bez areálu",
                ", od %s" % s.valid_from.strftime("%-d. %-m. %Y") if s.valid_from else "",
            )
            return pole
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def autocomplete_label(self, obj):
        # ClientCard.__str__ je schvalne prazdny (kvuli nadpisu v inline sekcich
        # na karte klienta) - autocomplete jinde (napr. u Klice) potrebuje
        # smysluplny popisek, proto se sestavuje tady zvlast.
        # Drive to byla metoda serialize_result, jenze tu Django na
        # ModelAdminu vubec nevola (je na AutocompleteJsonView) - popisek
        # tedy zustaval prazdny. Viz core/autocomplete.py.
        return obj.description or f"Karta {obj.client}"
    actions = ["kopie_karty"]

    def get_inlines(self, request, obj=None):
        """Plochy a najemne + sekce Klicu generovane z Trid
        (Nastaveni -> Tridy), ne napevno.

        Spolubydlici se ukazuji JEN u karet, ktere maji aspon jeden
        bytovy prostor (Unit.is_residential) - u kancelari a skladu ta
        sekce nedava smysl. Priznak je spolehlivy, pouziva se uz pro DPH
        podle §56a. U nove karty (obj=None) jeste zadne Plochy nejsou,
        takze se sekce objevi az po pridani bytu a ulozeni. Viz
        konverzace s Danielem 2026-08-19."""
        inlines = [CardUnitInline]
        if obj is not None and obj.card_units.filter(unit__is_residential=True).exists():
            inlines.append(CardOccupantInline)
        return [*inlines, *sekce_klicu()]

    @admin.action(description="Vytvořit kopii vybraných karet")
    def kopie_karty(self, request, queryset):
        for card in queryset:
            card.create_exact_copy()
        self.message_user(request, f"Vytvořeno {queryset.count()} kopií karet.")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path("nahled-karty/<int:card_id>/", self.admin_site.admin_view(self.nahled_view), name="core_clientcard_nahled"),
            path("kopie/<int:card_id>/", self.admin_site.admin_view(self.kopie_view), name="core_clientcard_kopie"),
            path(
                "kopie-klient/<int:card_id>/", self.admin_site.admin_view(self.kopie_klient_view),
                name="core_clientcard_kopie_klient",
            ),
            path(
                "generovat-kartu/<int:card_id>/", self.admin_site.admin_view(self.generate_card_and_download),
                name="core_clientcard_generovat",
            ),
            path(
                "report/plochy-konflikt/",
                self.admin_site.admin_view(self.report_plochy_konflikt_view),
                name="core_clientcard_report_plochy_konflikt",
            ),
            path(
                "report/najemne/",
                self.admin_site.admin_view(self.report_najemne_view),
                name="core_clientcard_report_najemne",
            ),
        ]
        return custom + urls

    def report_plochy_konflikt_view(self, request):
        """Report (Reporty v menu): najde Plochy (Unit), ktere jsou
        soucasne pres CardUnit napojene na aktivni Karty VICE RUZNYCH
        klientu najednou - typicky omylem dvakrat pronajata plocha.
        Existujici active_card_conflict() hlida jen "stejny klient, 2x
        aktivni karta ve stejnem arealu", ne tohle (ruzni klienti,
        stejna konkretni plocha) - viz konverzace s Danielem.

        Vysledky jsou SESKUPENE podle Arealu (ne jen sloupec v ploche
        tabulce) - dve ruzne Plochy se stejnym Nazvem v ruznych Arealech
        jsou u sebe v tabulce snadno k nerozeznani, Daniel si to
        spletl."""
        from django.shortcuts import render

        units = pronajimatele.omez(Unit.objects, "site", request).select_related(
            "site"
        ).prefetch_related(
            "card_units__card__client"
        ).order_by("site__name", "name")

        # Rozhoduje PREKRYV PLATNOSTI, ne pouhy pocet klientu. Dokud se
        # porovnaval jen priznak "aktivni", hlasila sestava jako konflikt
        # i normalni stridani najemcu - u AB 3.04 tri karty (CALAMARI do
        # 31. 7., CALAMARI do 31. 8., MI Roads od 1. 9.), ktere se ani
        # jednim dnem nepotkaji. Z jedenacti hlasenych radku bylo sest
        # planych. Daniel 2026-09-01.
        from datetime import date as _date

        DALEKO = _date(9999, 12, 31)

        def _prekryvaji(a, b):
            return max(a.valid_from, b.valid_from) <= min(a.valid_to or DALEKO,
                                                          b.valid_to or DALEKO)

        conflicts_by_site = {}
        for unit in units:
            active_cards = sorted(
                {cu.card for cu in unit.card_units.all() if cu.card.is_active},
                key=lambda c: (c.valid_from, c.client.name),
            )
            # Do vypisu jdou jen karty, ktere se s nekym opravdu potkavaji -
            # ta uzavrena z lonska ctenari nic nerekne.
            kolidujici = set()
            for i, prvni in enumerate(active_cards):
                for druha in active_cards[i + 1:]:
                    if prvni.client_id == druha.client_id:
                        continue
                    if _prekryvaji(prvni, druha):
                        kolidujici.add(prvni)
                        kolidujici.add(druha)
            if kolidujici:
                conflicts_by_site.setdefault(unit.site, []).append({
                    "unit": unit,
                    "cards": sorted(kolidujici, key=lambda c: (c.valid_from, c.client.name)),
                })

        groups = [
            {"site": site, "conflicts": conflicts}
            for site, conflicts in sorted(conflicts_by_site.items(), key=lambda kv: kv[0].name)
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": "Plochy přiřazené více klientům najednou",
            "groups": groups,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/clientcard/report_plochy_konflikt.html", context)

    @staticmethod
    def _plocha_se_dani(card_unit, klient):
        """Da se najem za tuhle Plochu zdanit?

        Najem je podle §56a od DPH osvobozeny a zdanit ho lze jen tehdy,
        kdyz jsou platci OBE strany - pronajimatel, ktery sam platcem
        neni, DPH naucovat nemuze a nema z ceho (areal DV je vedeny na
        fyzickou osobu neplatce). U stavby pro bydleni to neplati vubec:
        byt se podle §56a odst. 3 zdanit neda ani platci.

        Rozhoduje se za plochu, ne za kartu - karta muze mit plochy ve
        dvou arealech s ruznymi pronajimateli, nebo byt i nebytovy prostor
        zaroven. Viz Daniel 2026-08-24 (klient POKUS)."""
        unit = card_unit.unit
        pronajimatel = unit.site.landlord if unit.site.landlord_id else None
        return bool(
            klient.vat_payer
            and pronajimatel and pronajimatel.vat_payer
            and not unit.is_residential
        )

    def _zdanitelny_podil(self, card_units, klient):
        """Jaka cast najmu za dane Plochy se dani (0 az 1).

        Pouziva se pomer, ne soucet: castka k fakturaci uz je zkracena
        podle dnu platnosti karty a snizena o nefakturovanou cast, takze
        se k jednotlivym plocham primo priradit neda."""
        zaklad = sum(
            (cu.monthly_rent or Decimal("0") for cu in card_units), Decimal("0")
        )
        if not zaklad:
            return Decimal("0")
        zdanitelny = sum(
            (cu.monthly_rent or Decimal("0") for cu in card_units
             if self._plocha_se_dani(cu, klient)),
            Decimal("0"),
        )
        return zdanitelny / zaklad

    def _koeficient_dph_za_rok(self, period, site_ids):
        """Koeficient DPH (§76 ZDPH) za KALENDARNI ROK, ne za jeden mesic.

        Koeficient se ze zakona vypocitava z plneni za cely kalendarni
        rok (vyporadaci koeficient), takze jeden mesic nestaci - kazda
        Karta klienta do nej vstupuje jen za obdobi, ve kterych
        SKUTECNE PLATILA. To resi ClientCard.rent_for_period, ktera
        krati najem podle valid_from/valid_to (mimo platnost vraci nulu).
        Viz konverzace s Danielem 2026-08-19.

        Dve rozhodnuti, ktera stoji za vysvetleni:

        1) Bere se rok od ledna do VYBRANEHO obdobi (ne vsech 12 mesicu).
           Obdobi se zakladaji dopredu tlacitkem "Generovat pro cely rok",
           takze v DB uz existuji i mesice, ktere jeste nenastaly - ty by
           koeficient nafoukly o najem, ktery se jeste nestal. Kdyz se
           vybere prosinec, vyjde cely rok.

        2) Karty se beru podle PLATNOSTI (valid_from/valid_to), ne podle
           priznaku "Aktivní". Karta klienta, ktery behem roku odesel, je
           dnes neaktivni, ale najem za mesice, kdy tu byl, do koeficientu
           patri.

        Koeficient se pocita za JEDNU osobu, ne za jeden areal - proto ma
        vlastni vyber arealu (`site_ids`), nezavisly na filtru nad
        tabulkou. Danielova firma pronajima FM a NJ, kdezto DV je vedene
        na fyzickou osobu (neplatce DPH), takze do koeficientu firmy
        nepatri; vychozi zaskrtnuti se odvozuje z platcovstvi DPH
        pronajimatele arealu (Site.landlord.vat_payer).

        Filtruje se podle arealu KARTY (plochy na karte), ne klienta -
        a pocita se jen z ploch, ktere do vyberu spadaji. Karta by mela
        drzet plochy jednoho arealu, ale kdyz je rozkrocena pres vic,
        nesmi do koeficientu propadnout najem z arealu, ktery vybrany
        neni. Viz Daniel 2026-08-24."""
        from decimal import ROUND_CEILING

        rok = period.year
        obdobi_roku = list(
            Period.objects.filter(year=rok, month__lte=period.month).order_by("month")
        )
        if not obdobi_roku:
            return None

        karty = list(
            ClientCard.objects.filter(
                client__is_landlord=False,
                card_units__unit__site_id__in=site_ids,
            )
            .select_related("client")
            .prefetch_related("card_units__unit__site__landlord")
            .distinct()
        )
        vybrane = set(site_ids)

        mesice = []
        celkem_s_dph = celkem_bez_dph = celkem_nefakt = Decimal("0")
        for p in obdobi_roku:
            m_s_dph = m_bez_dph = m_nefakt = Decimal("0")
            for card in karty:
                plochy = [
                    cu for cu in card.card_units.all() if cu.unit.site_id in vybrane
                ]
                if not plochy:
                    continue
                najem = card.rent_for_period(p, plochy)
                if not najem:
                    continue  # karta v tomhle obdobi neplatila
                nefakt = min(card.rent_not_invoiced_for_period(p, plochy), najem)
                k_fakturaci = najem - nefakt
                m_nefakt += nefakt
                # Zdanitelna cast se urcuje za plochu (byt zdanit nelze
                # ani platci) - stejne jako v tabulce nad koeficientem.
                podil = self._zdanitelny_podil(plochy, card.client)
                m_s_dph += k_fakturaci * podil
                m_bez_dph += k_fakturaci * (1 - podil)
            mesice.append({
                "period": p,
                "s_dph": m_s_dph,
                "bez_dph": m_bez_dph,
                "nefakturovano": m_nefakt,
                "zaklad": m_s_dph + m_bez_dph,
            })
            celkem_s_dph += m_s_dph
            celkem_bez_dph += m_bez_dph
            celkem_nefakt += m_nefakt

        zaklad = celkem_s_dph + celkem_bez_dph
        if not zaklad:
            return None
        return {
            "rok": rok,
            "mesice": mesice,
            "pocet_obdobi": len(obdobi_roku),
            "cely_rok": len(obdobi_roku) == 12,
            "s_dph": celkem_s_dph,
            "bez_dph": celkem_bez_dph,
            "nefakturovano": celkem_nefakt,
            "zaklad": zaklad,
            "procenta": (celkem_s_dph / zaklad * 100).quantize(
                Decimal("1"), rounding=ROUND_CEILING
            ),
            "presne": (celkem_s_dph / zaklad * 100).quantize(Decimal("0.01")),
            "hranice": self._hranice_95(mesice, celkem_s_dph, celkem_bez_dph),
        }

    def _hranice_95(self, mesice, s_dph, bez_dph):
        """Co je potreba, aby koeficient dosahl zakonne hranice a odpocet
        se nekratil.

        §76 odst. 5 ZDPH: vypocteny koeficient se zaokrouhli na cele
        procento NAHORU a je-li roven nebo vyssi nez 95 %, povazuje se za
        100 % (plny narok na odpocet). Diky tomu zaokrouhleni staci, aby
        nezaokrouhlena hodnota presahla 94 % - proto se pocita s touhle
        hranici, ne s 95 %.

        Zbytek roku se odhaduje bezi POSLEDNIHO zapocteneho mesice - to
        nejlip odpovida soucasnemu stavu najemniku. Je to odhad, ne
        predpoved: kdyz nekdo prijde nebo odejde, cislo se zmeni.

        Vraci, co by bylo potreba dodat na zdanitelnem najmu, nebo
        naopak o kolik snizit osvobozeny - druha varianta byva
        realistictejsi. Viz konverzace s Danielem 2026-08-19."""
        from decimal import ROUND_CEILING

        # Hranice je "nad 94 %" - zaokrouhlenim nahoru se pak dostane na 95
        # a odpocet se nekrati. Cilime na 94,01 %, protoze presne 94,00 %
        # se zaokrouhli jeste na 94 a hranici by to netreflo (pri cileni na
        # rovnych 94 vychazelo "pridat 0 Kc", coz nic neresi).
        HRANICE = Decimal("94")
        CIL = Decimal("94.01")
        if not mesice:
            return None

        posledni = mesice[-1]
        zbyva = 12 - len(mesice)
        # odhad konce roku pri zachovani soucasneho stavu
        odhad_s = s_dph + posledni["s_dph"] * zbyva
        odhad_bez = bez_dph + posledni["bez_dph"] * zbyva
        odhad_zaklad = odhad_s + odhad_bez
        if not odhad_zaklad:
            return None

        odhad_pct = (odhad_s / odhad_zaklad * 100).quantize(Decimal("0.01"))
        podil = CIL / Decimal("100")
        staci = odhad_pct > HRANICE

        # kolik zdanitelneho najmu navic by bylo potreba
        chybi_zdanitelne = None
        # kolik osvobozeneho najmu by muselo ubyt
        snizit_osvobozene = None
        if not staci:
            chybi_zdanitelne = (
                (podil * odhad_zaklad - odhad_s) / (1 - podil)
            ).quantize(Decimal("1"), rounding=ROUND_CEILING)
            snizit_osvobozene = (
                odhad_zaklad - odhad_s / podil
            ).quantize(Decimal("1"), rounding=ROUND_CEILING)

        return {
            "zbyva_mesicu": zbyva,
            "odhad_s_dph": odhad_s,
            "odhad_bez_dph": odhad_bez,
            "odhad_zaklad": odhad_zaklad,
            "odhad_pct": odhad_pct,
            "odhad_zaokrouhlene": (odhad_s / odhad_zaklad * 100).quantize(
                Decimal("1"), rounding=ROUND_CEILING
            ),
            "staci": staci,
            "chybi_zdanitelne": chybi_zdanitelne,
            "snizit_osvobozene": snizit_osvobozene,
            "mesicne_zdanitelne": (
                (chybi_zdanitelne / zbyva).quantize(Decimal("1"), rounding=ROUND_CEILING)
                if chybi_zdanitelne is not None and zbyva else None
            ),
        }

    @staticmethod
    def _adresa_s_razenim(request, kod):
        """Soucasna adresa s prepsanym parametrem razeni."""
        parametry = request.GET.copy()
        parametry["razeni"] = kod
        return parametry.urlencode()

    def report_najemne_view(self, request):
        """Report (Reporty v menu): prehled najemneho po aktivnich Kartach -
        vyuziva jiz existujici CardUnit.monthly_rent (plocha x sazba/12).
        Mesicni castka za kartu se zaokrouhluje NAHORU na cele koruny
        (ROUND_CEILING, ne bezne zaokrouhleni) - takhle se najemne
        skutecne fakturuje, viz konverzace s Danielem. Rocni castka je
        odvozena z JIZ zaokrouhlene mesicni (x12), aby souhlasila se
        souctem 12 skutecne fakturovanych mesicu."""
        from decimal import ROUND_CEILING
        from django.shortcuts import render

        site_id = request.GET.get("site")
        sites = pronajimatele.arealy(request).order_by("name")

        # Prehled je vztazeny k OBDOBI: ukazuje karty, ktere v nem aspon
        # den plati, a najem zkraceny podle poctu aktivnich dni - jinak by
        # se rozchazel s vyuctovanim, kde se pausaly i sluzby uz kratí.
        # Viz konverzace s Danielem 2026-08-17.
        periods = Period.objects.all()
        period_id = request.GET.get("period")
        period = periods.filter(pk=period_id).first() if period_id else Period.current()

        # Vyber arealu pro KOEFICIENT - vlastni, nezavisly na filtru nad
        # tabulkou (koeficient je za jednu osobu, ne za jeden areal).
        # Bez parametru v URL se predvyplni arealy, jejichz PRONAJIMATEL je
        # platce DPH - u neplatce (Daniel jako fyzicka osoba u DV) koeficient
        # nedava smysl. Drive to drzel rucni priznak Site.in_vat_coefficient,
        # ktery presne kopiroval, komu areal patri. Viz Daniel 2026-08-24.
        if "koef_site" in request.GET:
            zadane = request.GET.getlist("koef_site")
            koef_site_ids = [
                s.pk for s in sites if str(s.pk) in zadane
            ]
        else:
            koef_site_ids = [
                s.pk for s in sites if s.landlord_id and s.landlord.vat_payer
            ]

        # Pronajimatel sam sobe najem neplati - jeho vlastni karty by prehled
        # jen nafukovaly. Pronajimatelu uz muze byt vic (kazdy areal svuj),
        # takze se vylucuji vsichni. Viz Daniel 2026-08-17 a 2026-08-24.
        cards = (
            pronajimatele.omez(
                ClientCard.objects.filter(is_active=True, client__is_landlord=False),
                "card_units__unit__site", request,
            )
            .select_related("client")
            .prefetch_related("card_units__unit__site__landlord")
            .order_by("client__name")
        )
        if site_id:
            cards = cards.filter(card_units__unit__site_id=site_id).distinct()

        rows = []
        period_start, period_end = period.date_range() if period else (None, None)
        # Sazba DPH se bere z vybraneho Obdobi (Period.vat_rate), aby zmena
        # sazby neprepocitala zpetne uz uzavrena obdobi. Bez obdobi (zadne
        # zalozene) se pouzije vychozi hodnota pole.
        sazba_dph = (
            period.vat_rate
            if period is not None
            else Period._meta.get_field("vat_rate").default
        ) / Decimal("100")
        for card in cards:
            card_units = list(card.card_units.all())
            # Filtr nad tabulkou vybira karty, ktere do arealu ZASAHUJI -
            # u karty rozkrocene pres dva arealy se ale musi zuzit i to, co
            # se z ni pocita, jinak filtr na DV ukaze i najem z ploch na FM.
            # Viz Daniel 2026-08-24 (klient POKUS).
            if site_id:
                card_units = [
                    cu for cu in card_units if str(cu.unit.site_id) == str(site_id)
                ]
            if not card_units:
                continue
            aktivnich_dnu = None
            if period is not None:
                aktivnich_dnu = card.active_days_in_period(period_start, period_end)
                if aktivnich_dnu <= 0:
                    continue  # karta v tomhle obdobi vubec neplati
            total_area = sum((cu.area_m2 or Decimal("0")) for cu in card_units)
            if period is not None:
                total_monthly = card.rent_for_period(period, card_units)
            else:
                raw_monthly = sum((cu.monthly_rent or Decimal("0") for cu in card_units), Decimal("0"))
                total_monthly = raw_monthly.quantize(Decimal("1"), rounding=ROUND_CEILING)
            # Plna mesicni sazba (nezkracena) - aby slo poznat, o kolik se
            # castka u castecne platne karty lisi.
            plny_mesic = sum(
                (cu.monthly_rent or Decimal("0") for cu in card_units), Decimal("0")
            ).quantize(Decimal("1"), rounding=ROUND_CEILING)
            # Cast najmu placena bez dokladu - do najmu patri, ale
            # nefakturuje se (viz CardUnit.rent_not_invoiced, scita se
            # pres ClientCard.rent_not_invoiced_for_period).
            if period is not None:
                nefakturovano = card.rent_not_invoiced_for_period(period, card_units)
            else:
                nefakturovano = sum(
                    (cu.rent_not_invoiced or Decimal("0") for cu in card_units),
                    Decimal("0"),
                )
            nefakturovano = min(nefakturovano, total_monthly)
            k_fakturaci = total_monthly - nefakturovano
            # Rocni castka pracuje s PLNYM mesicem (nezkracenym), takze se
            # od ni odecita taky nezkracena nefakturovana cast.
            nefakturovano_plny_mesic = min(
                sum((cu.rent_not_invoiced or Decimal("0") for cu in card_units), Decimal("0")),
                plny_mesic,
            )
            k_fakturaci_rocne = (plny_mesic - nefakturovano_plny_mesic) * 12
            podil_s_dph = self._zdanitelny_podil(card_units, card.client)
            zdanit = podil_s_dph > 0
            koef = 1 + sazba_dph * podil_s_dph
            rows.append({
                "client": card.client,
                "card": card,
                "sites": {cu.unit.site for cu in card_units},
                "area_m2": total_area,
                "monthly_rent": total_monthly,
                "nefakturovano": nefakturovano,
                "k_fakturaci": k_fakturaci,
                "k_fakturaci_s_dph": (k_fakturaci * koef).quantize(Decimal("0.01")),
                "plny_mesic": plny_mesic,
                "aktivnich_dnu": aktivnich_dnu,
                "dnu_v_obdobi": period.days_in_period if period else None,
                "castecne": period is not None and aktivnich_dnu < period.days_in_period,
                "s_dph": zdanit,
                "dph_castecne": Decimal("0") < podil_s_dph < 1,
                "podil_s_dph": (podil_s_dph * 100).quantize(Decimal("1")),
                "yearly_rent": plny_mesic * 12,
                "yearly_rent_s_dph": (k_fakturaci_rocne * koef).quantize(Decimal("0.01")),
            })

        # Razeni si vybira uzivatel v panelu nad tabulkou.
        #
        # Abecedne se NESMI radit prostym porovnanim retezcu: velka pismena
        # maji nizsi kod nez mala ("TVAROVKY" vyslo pred "Taneční") a
        # diakritika je uplne mimo rozsah ASCII, takze "TŠ JUST DANCE"
        # spadlo az za "Vodama". Klic proto jde na mala pismena a zbavi se
        # diakritiky - "Šimek" se tim zaradi k "S", coz je pro ceskou
        # abecedu spravne u vsech pismen krome ch/č/ř/š/ž jako
        # samostatnych "pismen" ve slovnikovem razeni; na seznam klientu
        # to bohate staci. Daniel 2026-08-26.
        import unicodedata

        def _abecedne(radek):
            jmeno = radek["client"].name.lower()
            return unicodedata.normalize("NFKD", jmeno).encode("ascii", "ignore").decode()

        razeni = request.GET.get("razeni") or "klient"
        if razeni == "najem":
            rows.sort(key=lambda r: (-r["monthly_rent"], _abecedne(r)))
        elif razeni == "vymera":
            rows.sort(key=lambda r: (-r["area_m2"], _abecedne(r)))
        else:
            razeni = "klient"
            rows.sort(key=_abecedne)
        total_monthly = sum((r["monthly_rent"] for r in rows), Decimal("0"))

        # Koeficient DPH (§76 ZDPH): podil zdanitelnych plneni na celkovem
        # plneni. Najem je podle §56a od DPH osvobozeny bez naroku na
        # odpocet; zdanit ho lze jen u najemce, ktery je platce DPH -
        # proto se tu rozhoduje podle Client.vat_payer. Overeno proti
        # ABRA Flexi za 07/2026 (core/management/commands/diag_dph_najem.py):
        # u vsech 37 faktur odpovidalo vycislene DPH tomuto priznaku, tzn.
        # neplatcum se najem s DPH nefakturuje. Viz konverzace s Danielem
        # 2026-08-18.
        #
        # Koeficient se ze zakona zaokrouhluje NAHORU na cele procento
        # a pocita se za KALENDARNI ROK, ne za jeden mesic - viz
        # _koeficient_dph_za_rok.
        koef = (
            self._koeficient_dph_za_rok(period, koef_site_ids)
            if period is not None and koef_site_ids
            else None
        )

        context = {
            **self.admin_site.each_context(request),
            "title": "Přehled nájemného",
            "sites": sites,
            "selected_site_id": int(site_id) if site_id else None,
            "periods": periods,
            "selected_period": period,
            "rows": rows,
            "razeni": razeni,
            # Jestli si arealy do koeficientu zvolil uzivatel sam. Formular
            # koeficientu je pak musi nest s sebou, jinak by prepnuti
            # koeficientu vratilo razeni na vychozi.
            "koef_zvoleno": "koef_site" in request.GET,
            # Prepinac razeni jsou ODKAZY, ne formular - kazdy si nese
            # celou soucasnou adresu s prepsanym "razeni", takze prepnuti
            # nemuze shodit Obdobi, Areal ani vybrane arealy do
            # koeficientu. request.GET.copy() zachova i vicehodnotovy
            # koef_site. Daniel 2026-08-26.
            "volby_razeni": [
                {
                    "kod": kod,
                    "popis": popis,
                    # Kotva na tabulku: po prepnuti se stranka nacte
                    # znovu a bez ni by uzivatel skoncil nahore a musel
                    # k tabulce zase sjizdet. Daniel 2026-08-26.
                    "url": "?%s#tabulka" % self._adresa_s_razenim(request, kod),
                    "aktivni": kod == razeni,
                }
                for kod, popis in (
                    ("klient", "Klient (A–Z)"),
                    ("najem", "Nájemné (od nejvyššího)"),
                    ("vymera", "Výměra (od největší)"),
                )
            ],
            "total_monthly": total_monthly,
            "total_yearly": total_monthly * 12,
            "total_monthly_s_dph": sum((r["k_fakturaci_s_dph"] for r in rows), Decimal("0")),
            "total_yearly_s_dph": sum((r["yearly_rent_s_dph"] for r in rows), Decimal("0")),
            "sazba_dph_pct": (sazba_dph * 100).normalize(),
            "koef": koef,
            "koef_sites": [
                {"site": s, "vybrany": s.pk in koef_site_ids} for s in sites
            ],
            "opts": self.model._meta,
        }
        return render(request, "admin/core/clientcard/report_najemne.html", context)

    @method_decorator(xframe_options_sameorigin)
    def nahled_view(self, request, card_id):
        """Karta jako PDF k ZOBRAZENI v prohlizeci, ne ke stazeni.

        Dekorator je nutny: projekt ma zapnuty XFrameOptionsMiddleware
        a Django bez nej posle X-Frame-Options: DENY, coz zakaze
        vykresleni i ve vlastnim ramu na tomtez webu - nahled pak zustal
        prazdny. Daniel 2026-08-26.

        Nic se neuklada - narozdil od generate_card_and_download se
        vysledek nezapisuje do pole Dokument. Podivat se na kartu tedy
        nezanechava stopu a nepretahuje uz vygenerovany soubor."""
        from io import BytesIO

        from django.http import HttpResponse

        from core.client_card_generator import generate_client_card_document

        card = self.get_queryset(request).filter(pk=card_id).first()
        if card is None:
            return self._presmeruj_cizi_kartu(request)

        buf = BytesIO()
        generate_client_card_document(card, buf)
        odpoved = HttpResponse(buf.getvalue(), content_type="application/pdf")
        odpoved["Content-Disposition"] = 'inline; filename="nahled_karty.pdf"'
        return odpoved

    def generate_card_and_download(self, request, card_id):
        from io import BytesIO
        from django.core.files.base import ContentFile
        from django.http import HttpResponse
        from django.shortcuts import redirect
        from core.client_card_generator import generate_client_card_document

        # Kontext pronajimatele - viz komentar u kopie_view.
        card = self.get_queryset(request).filter(pk=card_id).first()
        if card is None:
            return self._presmeruj_cizi_kartu(request)
        buf = BytesIO()
        generate_client_card_document(card, buf)
        filename = f"karta_najemce_{card.client.code or card.client.pk}_{card.pk}.pdf"
        card.document.save(filename, ContentFile(buf.getvalue()), save=True)

        response = HttpResponse(buf.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def generate_card_button(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if not obj.pk:
            return "Nejprve kartu uložte."
        url = reverse("admin:core_clientcard_generovat", args=[obj.pk])
        url_nahled = reverse("admin:core_clientcard_nahled", args=[obj.pk])
        # Tlacitko i miniatura vykresluje JEDNO pole, aby sedely vedle sebe -
        # dve samostatna readonly pole si admin sazi pod sebe.
        #
        # Zmensit musi byt SAMOSTATNE tlacitko: ve zvetsene podobe si
        # kliknuti bere prohlizec PDF (aby slo Kartou rolovat), takze na
        # obal uz se nedostane a zpatky by to neslo.
        #
        # Miniatura je normalne velky ramecek zmenseny pres CSS transform,
        # ne uzky <iframe>: prohlizec by v uzkem ramu nakreslil svou listu
        # a z Karty by nebylo videt nic. Nacita se rovnou pri otevreni
        # formulare, ale na pozadi - stranka na nej necheka. Daniel 2026-08-26.
        return format_html(
            '<div class="rx-karta-akce">'
            '<div class="rx-karta-tlacitka">'
            '<a href="{}" class="rx-btn rx-btn-primary">Generovat Kartu nájemce (.pdf)</a>'
            '</div>'
            '<div class="rx-karta-nahled" title="Klikni pro zvětšení" '
            'onclick="rxZvetsiKartu(this)">'
            '<iframe src="{}" title="Náhled Karty nájemce" loading="lazy"></iframe>'
            '<button type="button" class="rx-btn rx-btn-sm rx-karta-zmensit" '
            'onclick="event.stopPropagation();'
            'rxZvetsiKartu(this.closest(\'.rx-karta-nahled\'))">Zmenšit</button>'
            '</div>'
            '</div>'
            '<script>function rxZvetsiKartu(o){{'
            'o.classList.toggle("rx-zvetseno");'
            'o.title=o.classList.contains("rx-zvetseno")'
            '?"":"Klikni pro zvětšení";}}</script>',
            url, url_nahled,
        )
    generate_card_button.short_description = ""

    def _presmeruj_cizi_kartu(self, request):
        from django.shortcuts import redirect

        self.message_user(request, "Karta patří jinému pronajímateli.",
                          level=messages.ERROR)
        return redirect("admin:core_clientcard_changelist")

    def kopie_view(self, request, card_id):
        """Kopie karty pro TEHOZ klienta - zepta se, od kdy nova plati.

        Driv se kopie zakladala okamzite a zdedila platnost originalu,
        takze se obe data musela prepisovat rucne a snadno vznikla kopie
        se stejnym zacatkem jako original. Daniel 2026-09-01.

        Karta se zaklada NEAKTIVNI (create_exact_copy) - to je zamer:
        neaktivni karta do rozuctovani nevstupuje, takze si ji jde v klidu
        upravit, a teprve pri jejim zaskrtnuti jako aktivni projde
        ClientCard.clean kontrolou dvou soubeznych karet."""
        from django.shortcuts import redirect, render

        # Karta se bere pres self.get_queryset, tedy stejnym filtrem jako
        # seznam (PodlePronajimatele). Driv slo prostym ID v adrese
        # zkopirovat kartu cizniho pronajimatele - a tohle ZAPISUJE.
        # Daniel 2026-08-25.
        original = self.get_queryset(request).filter(pk=card_id).first()
        if original is None:
            return self._presmeruj_cizi_kartu(request)

        if request.method == "POST":
            platnost = self._datum_kopie(request, original)
            if platnost is None:
                return redirect(request.path)
            new_card = original.create_exact_copy(valid_from=platnost)
            self.message_user(
                request,
                "Kopie karty byla vytvořena s platností od %s. Je zatím "
                "neaktivní – zkontroluj ji a teprve pak zaškrtni Aktivní."
                % platnost.strftime("%-d. %-m. %Y"),
            )
            return redirect(f"/admin/core/clientcard/{new_card.pk}/change/")

        return render(request, "admin/core/clientcard/kopie_form.html", {
            **self.admin_site.each_context(request),
            "title": "Kopírovat kartu",
            "original": original,
            "opts": self.model._meta,
        })

    def _datum_kopie(self, request, original):
        """Datum 'platnost od' z formulare kopie, nebo None pri chybe."""
        from datetime import date

        zadane = (request.POST.get("valid_from") or "").strip()
        if not zadane:
            self.message_user(request, "Vyplň, od kdy má nová karta platit.",
                              level=messages.ERROR)
            return None
        try:
            platnost = date.fromisoformat(zadane)
        except ValueError:
            self.message_user(request, "Datum nedává smysl.", level=messages.ERROR)
            return None
        if platnost < original.valid_from:
            self.message_user(
                request,
                "Nová karta nemůže začít dřív (%s) než ta, ze které se "
                "kopíruje (%s)." % (platnost.strftime("%-d. %-m. %Y"),
                                    original.valid_from.strftime("%-d. %-m. %Y")),
                level=messages.ERROR,
            )
            return None
        return platnost

    def kopie_klient_view(self, request, card_id):
        """Kopie na jineho klienta - napr. kdyz si prostor pronajme novy najemce."""
        from django.shortcuts import redirect, render
        original = self.get_queryset(request).filter(pk=card_id).first()
        if original is None:
            return self._presmeruj_cizi_kartu(request)

        if request.method == "POST":
            new_client = Client.objects.filter(pk=request.POST.get("new_client")).first()
            if not new_client:
                self.message_user(request, "Musíš vybrat klienta, na kterého se má karta zkopírovat.", level=messages.ERROR)
                return redirect(request.path)
            platnost = self._datum_kopie(request, original)
            if platnost is None:
                return redirect(request.path)
            new_card = original.create_exact_copy(client=new_client, valid_from=platnost)
            self.message_user(
                request,
                "Kopie karty byla vytvořena pro klienta %s s platností od %s. "
                "Je zatím neaktivní – zkontroluj ji a teprve pak zaškrtni Aktivní."
                % (new_client, platnost.strftime("%-d. %-m. %Y")),
            )
            return redirect(f"/admin/core/clientcard/{new_card.pk}/change/")

        context = {
            **self.admin_site.each_context(request),
            "title": "Kopírovat kartu na nového klienta",
            "original": original,
            "clients": pronajimatele.klienti(
                request, Client.objects.filter(is_active=True)).order_by("name"),
            "opts": self.model._meta,
        }
        return render(request, "admin/core/clientcard/kopie_form.html", context)

    def add_view(self, request, form_url="", extra_context=None):
        """Barvy sekci se musi vlozit i na formulari NOVE Karty - driv se
        pridavaly jen v change_view, takze nova Karta mela sekce sede."""
        extra_context = extra_context or {}
        extra_context["invoice_class_colors"] = InvoiceClassColor.objects.all()
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["kopie_url"] = f"/admin/core/clientcard/kopie/{object_id}/"
        extra_context["kopie_klient_url"] = f"/admin/core/clientcard/kopie-klient/{object_id}/"
        extra_context["invoice_class_colors"] = InvoiceClassColor.objects.all()
        return super().change_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        from django.http import HttpResponseRedirect
        if "_continue" not in request.POST and "_addanother" not in request.POST and "_saveasnew" not in request.POST:
            return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)


class MeterReadingInline(TabularInline):
    model = MeterReading
    extra = 1
    fields = ("period", "reading_date", "value", "reset_from_value", "note", "photo")
    ordering = ("-period",)
    # Vypne Unfold radek s nazvem zaznamu ("668NT - 12/2025: 144095.000")
    # nad kazdym radkem - jen duplikoval hodnoty uz vidne ve sloupcich.
    # Zahlavi sloupcu (thead) zustava - bez nej neni jasne, ktery sloupec
    # je co (viz konverzace s Danielem).
    hide_title = True


@admin.register(Meter)
class MeterAdmin(PodlePronajimatele, DuplicateModelAdminMixin, ModelAdmin):
    cesta_k_arealu = "site"
    list_display = (
        "code_colored", "name", "site", "meter_type", "parent_meter", "supply_point",
        "reading_mode", "is_virtual", "unit_of_measure", "weight_unit_label",
    )
    list_select_related = ("site", "parent_meter", "supply_point")
    list_filter = ("site", "meter_type", "supply_point", "reading_mode", "is_virtual")
    search_fields = ("name", "code", "serial_number")
    autocomplete_fields = ("parent_meter", "supply_point")
    actions = ["duplicate_selected", "assign_supply_point"]
    inlines = [MeterReadingInline]

    def autocomplete_label(self, obj):
        """Popisek polozky v naseptavaci - pripisuje se areal.

        Meter.__str__ vraci jen kod, takze stejny kod ve dvou arealech
        (E_SPOL je ve FM i NJ, celkem 10 takovych kodu) vypadal v nabidce
        dvakrat uplne stejne a neslo poznat, ktery vybrat - Daniel na to
        narazil u Klice na Karte klienta. Meni se jen popisek v
        naseptavaci, ne __str__ (ten se pouziva v sestavach a PDF, kde je
        areal zrejmy z kontextu). Stejny vzor jako u ClientCardAdmin
        vyse. Viz konverzace s Danielem 2026-08-20."""
        return f"{obj.code or obj.name} ({obj.site.name})"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "meter_type":
            return invoice_class_choice_field(db_field)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @display(description="Kód", ordering="code")
    def code_colored(self, obj):
        return colored_by_meter_type(obj.code, obj.meter_type)

    @admin.action(description="Přiřadit vybraná měřidla k odběrnému místu…")
    def assign_supply_point(self, request, queryset):
        """Hromadne priradi vybrana meridla pod jedno Odberne misto (nebo
        odpoji, kdyz se zvoli prazdna volba) - aby Daniel nemusel
        rozklikavat kazde meridlo zvlast. Mezikrok s formularem, kde se
        vybere cilove odberne misto; vyber meridel se prenasi pres
        _selected_action. Viz konverzace s Danielem 2026-08-12."""
        if "apply" in request.POST:
            raw = request.POST.get("supply_point") or ""
            supply_point = SupplyPoint.objects.filter(pk=raw).first() if raw else None
            count = queryset.update(supply_point=supply_point)
            target = str(supply_point) if supply_point else "(žádné – odpojeno)"
            self.message_user(
                request, f"Přiřazeno {count} měřidel k odběrnému místu: {target}.",
                level=messages.SUCCESS,
            )
            return None

        from django.template.response import TemplateResponse
        return TemplateResponse(
            request,
            "admin/core/meter/assign_supply_point.html",
            {
                **self.admin_site.each_context(request),
                "title": "Přiřadit k odběrnému místu",
                "meters": queryset,
                "supply_points": pronajimatele.omez(
                SupplyPoint.objects, "site", request).select_related("site"),
                "action_name": "assign_supply_point",
                "selected_ids": queryset.values_list("pk", flat=True),
            },
        )

    def prepare_duplicate(self, copy, original):
        """Kod se NEKOPIRUJE (necha se prazdny) - je to kratky kod pro
        odkazovani ve vzorcich virtualnich meridel (Meter.formula), dve
        meridla se stejnym kodem by byla nejednoznacna (viz
        Meter._formula_tokens - Meter.objects.filter(site=..., code=...)
        by mohlo vratit spatne meridlo)."""
        copy.name = f"{original.name} (kopie)"
        copy.code = ""
    # U virtualniho meridla se spotreba pocita ze vzorce (viz
    # Meter.consumption_for) - "Zpusob zadavani odectu" se pak vubec
    # nepouziva, takze pole schovame (Unfold Alpine.js x-show).
    conditional_fields = {"reading_mode": "!is_virtual"}
    fieldsets = (
        (None, {
            "fields": (
                ("site", "code", "name"),
                ("meter_type", "unit_of_measure", "coefficient", "serial_number"),
                "reading_unit_of_measure",
                "display_order",
            )
        }),
        ("Odečty", {
            "fields": ("reading_mode",),
            "description": (
                "Většina měřidel hlásí kumulativní Stav. Pokud dodavatel hlásí "
                "rovnou Spotřebu za období (např. hlavní odběrné místo elektro), "
                "přepni na 'Spotřeba za období' - pak stačí zadávat odečet jen "
                "za aktuální měsíc, bez nutnosti znát předchozí stav."
            ),
        }),
        ("Hierarchie", {
            "fields": ("parent_meter",)
        }),
        ("Odběrné místo", {
            "fields": ("supply_point",),
            "description": (
                "Pod které odběrné místo (EAN) měřidlo fyzicky patří - slouží "
                "k reconciliaci 'dodáno vs. naměřeno' v přehledu spotřeb. "
                "Přívodní/fakturační měřidlo samotného odběru (např. 668_CELKEM) "
                "tu nech prázdné - to se nastavuje na Odběrném místě jako "
                "'Přívodní měřidlo'. Hromadně jde přiřadit i akcí v seznamu měřidel."
            ),
        }),
        ("Virtuální měřidlo", {
            "fields": (("is_virtual", "formula"),),
            "description": "Vyplnit pouze pokud se spotřeba nepočítá z odečtů, ale ze vzorce odkazujícího na kódy jiných měřidel (např. E_A1+E_AB1).",
        }),
        ("Podle váhy", {
            "fields": ("weight_unit_label",),
            "description": (
                "Vyplnit jen pokud jsou na toto měřidlo napojené klíče typu "
                "'Podle váhy' (typicky virtuální 'zbytkové' měřidlo jako "
                "E_SPOL) - krátký popis, co hodnota váhy znamená (m², počet "
                "osob, počet radiátorů...)."
            ),
        }),
    )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Doplni odkaz "Podíl vah" (viz change_form.html) primo na Podil
        vah teto Meridlo, pokud se nekde skutecne pouziva pro vypocet
        podilu - viz billing/weight_shares.find_items_for_meter."""
        from django.urls import reverse
        from billing.weight_shares import find_items_for_meter

        extra_context = extra_context or {}
        meter = self.get_queryset(request).filter(pk=object_id).first()
        if meter is not None:
            matching_items = find_items_for_meter(meter)
            base_url = reverse("admin:core_billingline_podil_vah")
            if len(matching_items) == 1:
                extra_context["podil_vah_url"] = f"{base_url}?item={matching_items[0].pk}&meter={meter.pk}"
            elif len(matching_items) > 1:
                extra_context["podil_vah_url"] = f"{base_url}?meter={meter.pk}"
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        from django.urls import path
        from django.http import JsonResponse
        from django.db.models import Q

        def meter_search(request):
            term = request.GET.get("term", "").strip()
            site_id = request.GET.get("site_id")
            meter_type = request.GET.get("meter_type")

            qs = pronajimatele.omez(Meter.objects, "site", request)
            if site_id:
                qs = qs.filter(site_id=site_id)
            if meter_type:
                qs = qs.filter(meter_type=meter_type)
            if term:
                qs = qs.filter(Q(name__icontains=term) | Q(code__icontains=term))

            qs = qs.order_by("name")[:50]
            return JsonResponse({"results": [{"id": m.id, "text": str(m)} for m in qs]})

        urls = super().get_urls()
        custom = [
            path(
                "search/",
                self.admin_site.admin_view(meter_search),
                name="core_meter_search",
            ),
            path(
                "report/neprirazena/",
                self.admin_site.admin_view(self.report_neprirazena_view),
                name="core_meter_report_neprirazena",
            ),
            path(
                "report/neprirazena/smazat/",
                self.admin_site.admin_view(self.report_neprirazena_smazat_view),
                name="core_meter_report_neprirazena_smazat",
            ),
            path(
                "report/spotreby/",
                self.admin_site.admin_view(self.report_spotreby_view),
                name="core_meter_report_spotreby",
            ),
            path(
                "report/stav-odectu/",
                self.admin_site.admin_view(self.report_stav_odectu_view),
                name="core_meter_report_stav_odectu",
            ),
        ]
        return custom + urls

    def report_spotreby_view(self, request):
        """Report (Reporty v menu): pro vybrane Obdobi (volitelne i Areal)
        ukaze spotrebu VSECH meridel podle hierarchie - odsazeni podle
        stromu parent_meter/children, u virtualnich meridel navic rozpad
        na jednotliva realna meridla podle Vzorce (Meter.consumption_leaves).
        Cil: po prepoctu Obdobi jde zkontrolovat, ze navazany strom mericí
        (fyzicky i vypocetni pres Vzorec) dava smysl - viz konverzace
        s Danielem."""
        from django.shortcuts import render

        period_id = request.GET.get("period")
        site_id = request.GET.get("site")

        periods = Period.objects.all()
        period = periods.filter(pk=period_id).first() if period_id else Period.current()

        sites = pronajimatele.arealy(request).order_by("name")
        site = sites.filter(pk=site_id).first() if site_id else None

        groups = []
        if period is not None:
            meters_qs = (
                pronajimatele.omez(Meter.objects, "site", request)
                .select_related("site", "parent_meter")
                .order_by("code")
            )
            if site is not None:
                meters_qs = meters_qs.filter(site=site)
            meters = list(meters_qs)

            # Strom se stavi jen z meridel VE VYBERU (napr. kdyz je vybrany
            # jeden Areal) - meridlo s rodicem mimo vyber se chova jako koren.
            meter_ids = {m.id for m in meters}
            children_by_parent = {}
            roots = []
            for m in meters:
                if m.parent_meter_id and m.parent_meter_id in meter_ids:
                    children_by_parent.setdefault(m.parent_meter_id, []).append(m)
                else:
                    roots.append(m)

            owned_cache = {}
            # {meter_id: o kolik podruzna meridla prevysila nadrazene} - v
            # sablone se u takoveho radku ukaze upozorneni.
            orezana_meridla = {}

            def owned_consumption(meter):
                """Vlastni spotreba meridla = surovy odecet minus VLASTNI
                spotreba vsech jeho primych deti (rekurzivne) - stejny
                princip jako billing/engine.py _owned_consumption, ale
                pocita se VZDY pro cely zobrazeny strom (ne jen pro
                fakturovane deti na jedne polozce) - tenhle report ma
                overit, ze fyzicky strom meridel dava smysl, ne
                reprodukovat vysledek konkretni Polozky. Bez toho by
                nadrazene meridlo (napr. E_A7) ukazovalo SVUJ surovy
                odecet (vc. vsech deti), coz vedle jednotlivych deti se
                stejnym souctem vypada jako nesmyslna duplicita - viz
                konverzace s Danielem 2026-08-12."""
                if meter.id in owned_cache:
                    return owned_cache[meter.id]
                raw = meter.consumption_for(period)
                if raw is None:
                    owned_cache[meter.id] = None
                    return None
                if meter.is_virtual:
                    # Virtualni meridlo pocita spotrebu uz ze sveho Vzorce
                    # (soucet zadanych meridel) - FK "Nadřazené měřidlo" u
                    # virtualniho meridla (pokud vubec existuje) NENI
                    # soucasti vypoctu spotreby, jen realna meridla maji
                    # fyzickou hierarchii master/podruzne. Kombinace obou
                    # (napr. E_SPOL) delala nesmyslny vysledek - viz
                    # konverzace s Danielem 2026-08-12.
                    owned_cache[meter.id] = raw
                    return raw
                # DULEZITE: odecita se SUROVA spotreba primych deti
                # (child.consumption_for), NE jejich uz zredukovana
                # "vlastni" hodnota (owned_consumption(child))! Kdyby se
                # odecitala vlastni hodnota, u vicevrstve hierarchie (napr.
                # A7 -> A4 -> A4KLIMA) by zbyla cast spotreby vnoucete
                # "schovana" uvnitr A7 (protoze od A7 by se odecetlo jen
                # zredukovanych 118 za A4, ne jeho skutecnych 134) - A7 by
                # tak fakticky obsahovalo spotrebu A4KLIMA dvakrat (jednou
                # schovane v sobe, jednou zvlast na radku A4KLIMA). Pri
                # SUROVE dedukci na kazde urovni zvlast to spravne
                # teleskopuje k soucet(vsechny "vlastni" hodnoty v podstromu)
                # == surovy odecet korene. Viz konverzace s Danielem
                # 2026-08-12 (E_A7 ma byt 473, ne 489).
                deduction = sum(
                    (child.consumption_for(period) or Decimal("0"))
                    for child in children_by_parent.get(meter.id, [])
                )
                result = raw - deduction
                if result < 0:
                    # Podruzna meridla namerila vic nez nadrazene - orezat na
                    # nulu (spotreba nemuze byt zaporna) a poznamenat si to,
                    # aby to v reportu neproslo bez povsimnuti. Stejne pravidlo
                    # jako v billing/engine.py _owned_consumption. Viz Daniel
                    # 2026-08-17.
                    orezana_meridla[meter.id] = -result
                    result = Decimal("0")
                owned_cache[meter.id] = result
                return result

            def add_row(meter, depth, rows, allowed_ids):
                consumption = owned_consumption(meter)
                indent_px = 8 + depth * 20
                leaves = None
                if meter.is_virtual:
                    # Kazdy list se zobrazi hodnotou, kterou skutecne
                    # prispiva do vzorce = jeho VLASTNI zbytek po odectu
                    # primych podruznych meridel (_consumption_net_of_children),
                    # ne surovy odecet. Bez toho listy nesedely se souctem
                    # virtualniho meridla v hlavicce (napr. E_SPOL = 776,
                    # ale +E_A7 se tisklo jako surovych 1214 misto vlastnich
                    # 473). Shoduje se s vlastni radkou E_A7 ve stromu vyse.
                    # Viz konverzace s Danielem 2026-08-13.
                    leaves = [
                        {
                            "meter": leaf, "sign_label": "+" if sign > 0 else "−",
                            "consumption": leaf._consumption_net_of_children(period),
                            "indent_px": indent_px + 20,
                        }
                        for leaf, sign in meter.consumption_leaves()
                    ]
                rows.append({
                    "meter": meter, "depth": depth, "consumption": consumption,
                    "indent_px": indent_px, "leaves": leaves, "is_virtual": meter.is_virtual,
                    "orezano": orezana_meridla.get(meter.id),
                })
                for child in children_by_parent.get(meter.id, []):
                    if child.id in allowed_ids:
                        add_row(child, depth + 1, rows, allowed_ids)

            # Prehled se cleni podle Meter.meter_type (Elektrina/Voda/...) a
            # uvnitr podle Odberneho mista (SupplyPoint): pro kazdy odber se
            # porovna "dodano" (privodni meridlo) vs. "namereno" (soucet
            # vlastnich spotreb realnych clenskych meridel) a rozdil =
            # ztraty/nezmereno. Meridla bez odberneho mista jdou do skupiny
            # "Nezarazena". Viz konverzace s Danielem 2026-08-12.
            supplies_qs = pronajimatele.omez(
                SupplyPoint.objects, "site", request
            ).select_related("main_meter", "site")
            if site is not None:
                supplies_qs = supplies_qs.filter(site=site)
            supplies = list(supplies_qs)

            # Privodni meridla odberu (a u virtualniho privodu i jeho slozky,
            # napr. 668_CELKEM -> 668NT/668VT) NEJSOU podruzne clenske
            # meridlo - patri k odberu jako "dodano". Vynechavame je z
            # clenskych i nezarazenych skupin bez ohledu na to, jak ma
            # dotycne meridlo nastaveny supply_point (aby se dodavka
            # nezapocitala jeste jednou i jako namereno).
            supply_side_ids = set()
            for sp in supplies:
                if sp.main_meter_id:
                    supply_side_ids.add(sp.main_meter_id)
                    if sp.main_meter and sp.main_meter.is_virtual:
                        for leaf, _s in sp.main_meter.consumption_leaves():
                            supply_side_ids.add(leaf.id)

            def sum_measured(bucket_rows):
                """Namereno = soucet VLASTNICH spotreb realnych (nevirtualnich)
                clenskych meridel. Virtualni meridlo (napr. E_SPOL) je jen
                agregace uz zapocitanych realnych meridel - zobrazi se
                seede, ale do souctu se nepricita (jinak by jeho slozky
                byly 2x)."""
                return sum(
                    (r["consumption"] or Decimal("0"))
                    for r in bucket_rows if not r["is_virtual"]
                )

            def build_bucket_rows(member_meters):
                """Radky pro jednu skupinu (odberne misto / Nezarazena) vc.
                stromu parent/child JEN v ramci teto skupiny - meridlo,
                jehoz rodic je jinde, se chova jako koren."""
                member_ids = {m.id for m in member_meters}
                bucket_rows = []
                for m in member_meters:
                    if m.parent_meter_id not in member_ids:
                        add_row(m, 0, bucket_rows, member_ids)
                return bucket_rows

            supplies_by_type = {}
            for sp in supplies:
                supplies_by_type.setdefault(sp.meter_type, []).append(sp)

            members_by_supply = {}
            unassigned_by_type = {}
            for m in meters:
                if m.id in supply_side_ids:
                    continue
                if m.supply_point_id:
                    members_by_supply.setdefault(m.supply_point_id, []).append(m)
                else:
                    unassigned_by_type.setdefault(m.meter_type, []).append(m)

            unit_defaults = InvoiceClassColor.default_unit_map()
            for type_code, type_label in InvoiceClassColor.choices():
                type_supplies = supplies_by_type.get(type_code, [])
                type_unassigned = unassigned_by_type.get(type_code, [])
                if not type_supplies and not type_unassigned:
                    continue

                supply_blocks = []
                total_dodano = None
                total_namereno = Decimal("0")

                for sp in type_supplies:
                    member_meters = members_by_supply.get(sp.id, [])
                    bucket_rows = build_bucket_rows(member_meters)

                    # Spolecna spotreba = hodnota virtualnich clenskych meridel
                    # (napr. E_SPOL = A7+A8+A9+E_D_VS) - merena spolecna cast,
                    # ktera se rozpocitava vahou. Jeji slozky (listy vzorce,
                    # napr. A7/A8/A9/D_VS) se do "podmeru" nepocitaji podruhe -
                    # jsou uz zahrnute ve spolecne. Viz Daniel 2026-08-12.
                    spolecne = Decimal("0")
                    spolecne_leaf_ids = set()
                    for m in member_meters:
                        if m.is_virtual:
                            val = owned_consumption(m)
                            if val is not None:
                                spolecne += val
                            for leaf, _s in m.consumption_leaves():
                                spolecne_leaf_ids.add(leaf.id)

                    # Podmery = vlastni spotreba realnych clenskych meridel
                    # najemniku (bez spolecnych slozek E_SPOL).
                    podmery = Decimal("0")
                    for m in member_meters:
                        if m.is_virtual or m.id in spolecne_leaf_ids:
                            continue
                        val = owned_consumption(m)
                        if val is not None:
                            podmery += val

                    namereno = podmery + spolecne
                    total_namereno += namereno

                    dodano = owned_consumption(sp.main_meter) if sp.main_meter_id else None
                    main_leaves = None
                    if sp.main_meter and sp.main_meter.is_virtual:
                        main_leaves = [
                            {"meter": leaf, "consumption": leaf._consumption_net_of_children(period)}
                            for leaf, _s in sp.main_meter.consumption_leaves()
                        ]

                    # Kaskada: Dodano (faktura/privod) - Zakonna ztrata (%) =
                    # Realne dodane; z nej po odectu podmeru zbyva "rozpocitano
                    # vahou", z toho merena Spolecna (E_SPOL) a zbytek jsou
                    # Skutecne ztraty (promereni/pozdni odecet). Viz Daniel
                    # 2026-08-12. 4 % zakonna ztrata jen u velkoodberu FM.
                    # Faktura UZ ztratu OBSAHUJE (dodavatel k realne dodanemu
                    # pripocita 4 %), takze realne = faktura / (1 + %/100),
                    # ne faktura x (1 - %/100). Viz oprava Daniel 2026-08-12
                    # (7436 kWh se 4 % => 7436/1,04 = 7150, ne 0,96x7436).
                    # Dve RUZNE ztraty, ktere se nesmi michat dohromady
                    # (Daniel 2026-08-16):
                    #  - ZAKONNA ztrata (4 %, jen odbery TEDOM): dodavatel ji
                    #    uctuje vzdy, neni to zadny strop ani rezerva. Vzdy
                    #    kladna.
                    #  - ZTRATA MERENI: rozdil mezi tim, co po odectu zakonne
                    #    ztraty realne doslo, a tim, co nametrily nase podmery.
                    #    Muze vyjit i ZAPORNE (namerili jsme vic) - typicky
                    #    casovym posunem mezi nasim odectem a odectem
                    #    dodavatele; priste to vyjde opacne. Zaporna hodnota
                    #    jde ve prospech klientu a NENI chyba, proto se
                    #    zobrazuje se svym skutecnym znamenkem, ne prebarvena
                    #    na "vejde se do rezervy" (to drivejsi zneni rozpor
                    #    jen zamaskovalo).
                    zakonne = realne = vahou = skutecne = None
                    skutecne_pct = None
                    if dodano is not None:
                        pct = sp.legal_loss_pct or Decimal("0")
                        realne = dodano / (Decimal("1") + pct / Decimal("100"))
                        zakonne = dodano - realne
                        vahou = realne - podmery
                        skutecne = vahou - spolecne
                        total_dodano = (total_dodano or Decimal("0")) + dodano
                        if realne:
                            skutecne_pct = skutecne / realne * Decimal("100")

                    supply_blocks.append({
                        "supply": sp, "dodano": dodano, "zakonne": zakonne,
                        "realne": realne, "podmery": podmery, "spolecne": spolecne,
                        "vahou": vahou, "skutecne": skutecne,
                        "skutecne_pct": skutecne_pct,
                        "namereno": namereno, "pct": sp.legal_loss_pct,
                        "rows": bucket_rows, "main_meter": sp.main_meter,
                        "main_leaves": main_leaves,
                    })

                unassigned_block = None
                if type_unassigned:
                    u_rows = build_bucket_rows(type_unassigned)
                    u_namereno = sum_measured(u_rows)
                    total_namereno += u_namereno
                    unassigned_block = {"rows": u_rows, "namereno": u_namereno}

                # Jednotka se bere z reálných měřidel dané skupiny (ne napevno) -
                # respektuje skutečnou jednotku (teplo FM = kWh, jinde třeba GJ).
                type_unit = next(
                    (m.unit_of_measure for m in meters
                     if m.meter_type == type_code and m.unit_of_measure),
                    unit_defaults.get(type_code, ""),
                )
                groups.append({
                    "label": type_label,
                    "unit": type_unit,
                    "supplies": supply_blocks,
                    "unassigned": unassigned_block,
                    "total_dodano": total_dodano,
                    "total_namereno": total_namereno,
                })

        context = {
            **self.admin_site.each_context(request),
            "title": "Spotřeby měřidel podle hierarchie",
            "periods": periods,
            "selected_period": period,
            "sites": sites,
            "selected_site": site,
            "groups": groups,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/meter/report_spotreby.html", context)

    def _unassigned_meters_queryset(self, request=None):
        """Meridla, ktera nejsou pouzita VUBEC - ani jako hlavni meridlo
        polozky (ServicePoolItem.meter), ani napojene na zadny Klic
        (AllocationKey.meter), ani jako nadrazene meridlo jineho meridla,
        ani jako vychozi sluzba plochy (UnitService.meter). Typicky
        pozustatek po smazane/prejmenovane strukture (viz konverzace s
        Danielem - E_VLASTNI/W_VLASTNI/T_SPOLECNA cistka).

        Sdileno mezi report_neprirazena_view (zobrazeni) a
        report_neprirazena_smazat_view (mazani) - mazaci view si tohle
        pocita znovu samo, aby nedoverovalo tomu, co prislo z formulare
        (mezitim se meridlo mohlo stat pouzitym)."""
        used_as_item_meter = ServicePoolItem.objects.exclude(meter__isnull=True).values_list("meter_id", flat=True)
        used_as_key_meter = AllocationKey.objects.exclude(meter__isnull=True).values_list("meter_id", flat=True)
        used_as_parent = Meter.objects.exclude(parent_meter__isnull=True).values_list("parent_meter_id", flat=True)
        used_as_unit_service_meter = UnitService.objects.exclude(meter__isnull=True).values_list("meter_id", flat=True)

        # "Pouzito" se zjistuje NAPRIC obema pronajimateli zamerne - kdyby
        # se pouziti hledalo jen v kontextu, vypadalo by cizi pouzite
        # meridlo jako nepouzite a slo by ho smazat. Az vysledek se omezi
        # na kontext. Viz Daniel 2026-08-25.
        qs = (
            Meter.objects.select_related("site")
            .exclude(pk__in=used_as_item_meter)
            .exclude(pk__in=used_as_key_meter)
            .exclude(pk__in=used_as_parent)
            .exclude(pk__in=used_as_unit_service_meter)
            .order_by("site__name", "code")
        )
        if request is not None:
            qs = pronajimatele.omez(qs, "site", request)
        return qs

    def _formula_protected_meter_ids(self):
        """{meter_id: [nazvy virtualnich meridel, ktera na nej odkazuji ve
        Vzorci]} - tato meridla se NESMI smazat, i kdyz jinak vypadaji
        jako nepouzita: Vzorec odkazuje na meridlo podle KODU (viz
        Meter._formula_tokens), ne pres FK/on_delete, takze zadna DB
        vazba by smazani samo o sobe nezabranila."""
        protected = {}
        virtual_meters = Meter.objects.filter(is_virtual=True).exclude(formula="")
        for vm in virtual_meters:
            for referenced_meter, _sign in vm._formula_tokens():
                protected.setdefault(referenced_meter.id, []).append(str(vm))
        return protected

    def report_stav_odectu_view(self, request):
        """Sestava (Reporty v menu): stav odectu za obdobi po arealech.

        Odpovida na jedinou otazku - "muzu za tohle obdobi pocitat?".
        Ke kazdemu arealu: kolik meridel ma odecet, kde chybi, kde chybi
        fotka, ktere spotreby vypadaji neverohodne a jestli uz to spravce
        uzavrel. Daniel 2026-09-01.

        Neverohodnost pocita STEJNA funkce, ktera hlida zadavani odectu
        (meters.views._podezrela_spotreba) - aby sestava a obrazovka
        spravce nerikaly kazda neco jineho.
        """
        from django.shortcuts import render

        from meters.views import _meridla_bez_odectu, _podezrela_spotreba

        periods = Period.objects.all()
        period_id = request.GET.get("period")
        period = periods.filter(pk=period_id).first() if period_id else Period.current()

        skupiny = []
        if period is not None:
            for site in pronajimatele.arealy(request).order_by("name"):
                meridla = list(Meter.objects.filter(site=site, is_virtual=False).order_by("code"))
                odecty = {
                    r.meter_id: r
                    for r in MeterReading.objects.select_related("meter").filter(
                        period=period, meter__site=site)
                }
                chybejici = [m for m in meridla if m.id not in odecty]
                bez_foto = [odecty[m.id] for m in meridla if m.id in odecty and not odecty[m.id].photo]

                podezrele = []
                for m in meridla:
                    r = odecty.get(m.id)
                    if r is None:
                        continue
                    spotreba = m.consumption_for(period)
                    duvod = _podezrela_spotreba(m, period, spotreba) if spotreba is not None else None
                    if duvod:
                        podezrele.append({"reading": r, "consumption": spotreba, "duvod": duvod})

                skupiny.append({
                    "site": site,
                    "meridel": len(meridla),
                    "s_odectem": len(meridla) - len(chybejici),
                    "chybejici": chybejici,
                    "bez_foto": bez_foto,
                    "podezrele": podezrele,
                    "uzavreno": ReadingsClosure.objects.filter(
                        period=period, site=site).select_related("closed_by").first(),
                })

        context = {
            **self.admin_site.each_context(request),
            "title": "Stav odečtů za období",
            "periods": periods,
            "selected_period": period,
            "skupiny": skupiny,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/meter/report_stav_odectu.html", context)

    def report_neprirazena_view(self, request):
        """Report (Reporty v menu) s moznosti hromadne smazat vybrana
        nepouzita meridla (viz report_neprirazena_smazat_view)."""
        from django.shortcuts import render

        unused = list(self._unassigned_meters_queryset(request))
        protected = self._formula_protected_meter_ids()
        for m in unused:
            m.formula_used_by = protected.get(m.id)

        context = {
            **self.admin_site.each_context(request),
            "title": "Nepřiřazená měřidla",
            "meters": unused,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/meter/report_neprirazena.html", context)

    def report_neprirazena_smazat_view(self, request):
        """Hromadne smazani vybranych nepouzitych meridel z reportu.
        Pred smazanim si sam znovu spocita, ktera meridla jsou skutecne
        nepouzita a nejsou chranena Vzorcem (nedoveruje checkboxum z
        formulare) - cokoliv vybraneho mimo tuhle bezpecnou mnozinu se
        jen preskoci a nahlasi, misto aby to spadlo nebo se smazalo
        neco, co nema."""
        from django.contrib import messages
        from django.shortcuts import redirect

        if request.method != "POST":
            return redirect("admin:core_meter_report_neprirazena")

        requested_ids = {int(pk) for pk in request.POST.getlist("meter_ids") if pk.isdigit()}
        if not requested_ids:
            messages.warning(request, "Nebylo vybráno žádné měřidlo.")
            return redirect("admin:core_meter_report_neprirazena")

        safe_ids = set(
            self._unassigned_meters_queryset(request).values_list("pk", flat=True)
        )
        safe_ids -= set(self._formula_protected_meter_ids().keys())

        to_delete = requested_ids & safe_ids
        skipped = requested_ids - safe_ids

        if to_delete:
            # Omezeno na kontext, aby seznam id z formulare nemohl sahnout
            # na meridla druheho pronajimatele.
            mazana = pronajimatele.omez(Meter.objects, "site", request).filter(pk__in=to_delete)
            deleted_names = list(mazana.values_list("name", flat=True))
            mazana.delete()
            messages.success(request, f"Smazáno {len(to_delete)} měřidel: {', '.join(deleted_names)}.")
        if skipped:
            messages.error(
                request,
                f"{len(skipped)} měřidel se nepodařilo smazat (mezitím se stala použitá, nebo jsou "
                "součástí Vzorce jiného měřidla) - stránka se obnovila, zkontroluj a zkus to znovu.",
            )
        return redirect("admin:core_meter_report_neprirazena")


@admin.register(Period)
class PeriodAdmin(ModelAdmin):
    list_display = (
        "__str__", "current_badge", "status_badge", "days_in_period",
        "vat_rate", "period_actions",
    )
    list_editable = ("vat_rate",)
    list_filter = ("status", "is_current")
    ordering = ("-year", "-month")
    actions = [
        "spocitat_rozuctovani", "zkontrolovat_co_zadat", "vygenerovat_chybejici_naklady",
        "dotahnout_fakturovana_mnozstvi",
        "nastavit_jako_aktualni", "uzavrit_obdobi", "znovu_otevrit_obdobi",
    ]
    # Tlacitko "Generovat pro celý rok" nad tabulkou - puvodne zkoušeno
    # pres object-tools-items blok jako u change_form, ale na
    # zmenovnem seznamu je "object-tools" soucast globalni horni
    # listy (nav-global-side), ne radku nad tabulkou - rozbilo to
    # layout (viz konverzace s Danielem). list_before_template je
    # bezpecny Unfold hook primo nad tabulkou (stejny princip jako
    # list_after_template u grafu inflace).
    list_before_template = "admin/core/period/generovat_rok_button.html"

    def get_changeform_initial_data(self, request):
        # Pri pridavani noveho Obdobi predvyplnit rok aktualnim rokem
        # (nejcasteji se zaklada obdobi letoska). Viz Daniel.
        from datetime import date
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("year", date.today().year)
        return initial

    @display(
        description="Stav", ordering="status",
        label={Period.Status.OPEN.label: "success", Period.Status.CLOSED.label: "danger"},
    )
    def status_badge(self, obj):
        return obj.get_status_display()

    @display(description="Aktuální", ordering="is_current", boolean=True)
    def current_badge(self, obj):
        return obj.is_current

    @admin.action(description="Nastavit jako aktuální období (předvyplní se v sestavách)")
    def nastavit_jako_aktualni(self, request, queryset):
        """Aktualni obdobi je jen jedno - z vyberu se bere to nejnovejsi
        a ostatni se odznaci (dela Period.save())."""
        period = queryset.order_by("-year", "-month").first()
        if period is None:
            return
        period.is_current = True
        period.save()
        self.message_user(
            request, f"Aktuální období je nyní {period} - předvyplní se ve všech sestavách."
        )

    def _period_action_button(self, url, label, varianta, confirm_text):
        """Tlacitko akce pro JEDNO obdobi primo v radku tabulky.

        POZOR na vlastni <form>: bunka tabulky je uvnitr velkeho
        <form id="changelist-form"> (hromadne akce dole), a vnorene
        formulare HTML nepovoluje - prohlizec vnitrni <form> ZAHODI a
        prvni </form> mu navic predcasne uzavre ten vnejsi. Dopadalo to
        tak, ze tlacitka v PRVNIM radku odesilala changelist-form, tedy
        akci vybranou v combu dole (klidne i mazani), zatimco v dalsich
        radcich uz fungovala spravne. Overeno v prohlizeci
        2026-08-19 (button.form ukazoval na changelist-form).

        Reseni bez vnoreni: tlacitko je bezny submit changelist-formu, ale
        pres HTML5 `formaction` si prepise cil odeslani jen pro sebe.
        CSRF token si bere z changelist-formu ({% csrf_token %} tam je).
        Data hromadnych akci, ktera se pritom odeslou, nas pohled ignoruje -
        obdobi bere z URL."""
        from django.utils.html import format_html
        return format_html(
            '<button type="submit" formaction="{}" formmethod="post" formnovalidate '
            'onclick="return confirm(\'{}\');" class="{}">{}</button>',
            url, confirm_text, f"rx-btn rx-btn-sm {varianta}".strip(), label,
        )

    def _period_link_button(self, url, label, varianta="", nove_okno=True):
        from django.utils.html import format_html
        return format_html(
            '<a href="{}"{} class="{}">{}</a>',
            url, format_html(' target="_blank"') if nove_okno else "", f"rx-btn rx-btn-sm {varianta}".strip(), label,
        )

    def period_actions(self, obj):
        from django.urls import reverse
        from django.utils.safestring import mark_safe

        uzavrene = obj.status == Period.Status.CLOSED
        buttons = []
        # U uzavreneho obdobi nema smysl nabizet ani odecty, ani vypocet -
        # odecty jdou jen do otevreneho obdobi (meters/views.py hlida
        # period_closed) a prepocet engine odmitne
        # (BillingPeriodClosedError). Zbyde jen "Otevřít". Viz konverzace
        # s Danielem 2026-08-19.
        if not uzavrene:
            odecty_url = f"{reverse('odecty')}?period={obj.pk}"
            buttons.append(self._period_link_button(odecty_url, "Zadat odečty"))
            # Vypocet je ODKAZ, ne POST tlacitko - otevre mezistranku
            # s vyberem arealu (viz vypocet_view).
            buttons.append(self._period_link_button(
                reverse("admin:core_period_vypocet", args=[obj.pk]),
                "Výpočet", "rx-btn-primary", nove_okno=False,
            ))
        # Otevrit ma smysl jen u uzavreneho obdobi a naopak - u
        # aktualniho stavu by tlacitko nic nezmenilo (viz konverzace
        # s Danielem).
        if uzavrene:
            buttons.append(self._period_action_button(
                reverse("admin:core_period_otevrit", args=[obj.pk]),
                "Otevřít", "rx-btn-success", f"Znovu otevřít {obj}?",
            ))
        else:
            buttons.append(self._period_action_button(
                reverse("admin:core_period_zavrit", args=[obj.pk]),
                "Zavřít", "rx-btn-danger", f"Uzavřít {obj}? Rozúčtování už pak nepůjde přepočítat.",
            ))
        return mark_safe(" ".join(buttons))
    period_actions.short_description = "Akce"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path(
                "<int:period_id>/otevrit/",
                self.admin_site.admin_view(self.otevrit_view),
                name="core_period_otevrit",
            ),
            path(
                "<int:period_id>/zavrit/",
                self.admin_site.admin_view(self.zavrit_view),
                name="core_period_zavrit",
            ),
            path(
                "<int:period_id>/vypocet/",
                self.admin_site.admin_view(self.vypocet_view),
                name="core_period_vypocet",
            ),
            path(
                "generovat-rok/",
                self.admin_site.admin_view(self.generovat_rok_view),
                name="core_period_generovat_rok",
            ),
        ]
        return custom + urls

    def generovat_rok_view(self, request):
        """Tlacitko "Generovat pro celý rok" (object-tools na zmenovnem
        seznamu, viz templates/admin/core/period/change_list.html) -
        misto zakladani vsech 12 Obdobi rocne rucne jedno po druhem.
        Stejny osvedceny vzor jako ContractAdmin.generovat_karty_inflace
        (GET = mezistrankaformular, POST s "apply" = provede se) - Unfold
        samo o sobe modalni okno s vlastnim polem nema, tohle je bezna
        Django admin akce/stranka, kterou Unfold jen automaticky styluje."""
        from datetime import date
        from django.shortcuts import render, redirect

        if request.method == "POST":
            try:
                year = int(request.POST.get("year"))
            except (TypeError, ValueError):
                self.message_user(request, "Zadej platný rok.", level=messages.ERROR)
                return redirect("admin:core_period_generovat_rok")
            if not (2000 <= year <= 2100):
                self.message_user(request, "Zadej rok mezi 2000 a 2100.", level=messages.ERROR)
                return redirect("admin:core_period_generovat_rok")

            created = 0
            for month in range(1, 13):
                _, was_created = Period.objects.get_or_create(year=year, month=month)
                if was_created:
                    created += 1
            skipped = 12 - created
            text = f"Vytvořeno {created} období pro rok {year}."
            if skipped:
                text += f" {skipped} už existovalo, přeskočeno."
            self.message_user(request, text, level=messages.SUCCESS if created else messages.WARNING)
            return redirect("admin:core_period_changelist")

        context = {
            **self.admin_site.each_context(request),
            "title": "Generovat období pro celý rok",
            "current_year": date.today().year,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/period/generovat_rok.html", context)

    def _obdobi_ma_data(self, period):
        """Ma obdobi navazana data, ktera by se pri smazani ztratila?
        Vsechny tyhle vazby jsou on_delete=CASCADE."""
        return (
            period.readings.exists()
            or period.cost_entries.exists()
            or period.price_list.exists()
            or period.billing_lines.exists()
        )

    def has_delete_permission(self, request, obj=None):
        """Obdobi s daty smazat NEJDE - kaskada by vzala odecty meridel,
        naklady, ceniky i cely spocitany vyuctovani. U 07/2026 to bylo
        411 zaznamu (115 odectu + 10 nakladu + 285 radku vyuctovani).
        Nabidka "Odstranit" je vestavena akce Djangu, ktera se ve
        vyberu dole objevuje sama a `actions` v kodu ji nevypina, takze
        pojistka musi byt tady. Viz konverzace s Danielem 2026-08-19.

        Prazdna obdobi (typicky omylem vygenerovana pres "Generovat pro
        celý rok") smazat jdou - jinak by je neslo uklidit."""
        if obj is not None and self._obdobi_ma_data(obj):
            return False
        return super().has_delete_permission(request, obj)

    def _redirect_back(self, request):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("admin:core_period_changelist"))

    def otevrit_view(self, request, period_id):
        from django.shortcuts import get_object_or_404
        if request.method != "POST":
            return self._redirect_back(request)
        period = get_object_or_404(Period, pk=period_id)
        period.status = Period.Status.OPEN
        period.save(update_fields=["status"])
        self.message_user(
            request, f"{period}: znovu otevřeno - rozúčtování teď jde přepočítat.", level=messages.WARNING
        )
        return self._redirect_back(request)

    def zavrit_view(self, request, period_id):
        from django.shortcuts import get_object_or_404
        if request.method != "POST":
            return self._redirect_back(request)
        period = get_object_or_404(Period, pk=period_id)
        period.status = Period.Status.CLOSED
        period.save(update_fields=["status"])
        self.message_user(
            request, f"{period}: uzavřeno - rozúčtování už nepůjde přepočítat.", level=messages.SUCCESS
        )
        return self._redirect_back(request)

    def vypocet_view(self, request, period_id):
        """Vypocet rozuctovani za JEDNO obdobi, s volbou arealu.

        GET = mezistranka s vyberem arealu, POST = provede se. Stejny
        vzor jako generovat_rok_view. Driv tlacitko v radku POSTovalo
        rovnou a pocitalo vzdy VSECHNY arealy - vybrat jeden slo jen
        pres hromadne akce dole, coz nebylo poznat. Viz konverzace
        s Danielem 2026-08-19."""
        from django.shortcuts import get_object_or_404, redirect, render

        period = get_object_or_404(Period, pk=period_id)

        if request.method == "POST":
            site_id = request.POST.get("site") or ""
            site = None
            if site_id:
                site = pronajimatele.arealy(request).filter(pk=site_id).first()
                if site is None:
                    self.message_user(request, "Neznámý areál.", level=messages.ERROR)
                    return redirect("admin:core_period_changelist")
            self._spocitat_rozuctovani(request, Period.objects.filter(pk=period.pk), site=site)
            return redirect("admin:core_period_changelist")

        context = {
            **self.admin_site.each_context(request),
            "title": f"Výpočet rozúčtování – {period}",
            "period": period,
            "sites": pronajimatele.arealy(request).order_by("name"),
            "je_uzavrene": period.status == Period.Status.CLOSED,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/period/vypocet.html", context)

    def get_actions(self, request):
        actions = super().get_actions(request)
        for site in pronajimatele.arealy(request):
            action_name = f"spocitat_rozuctovani_site_{site.pk}"
            actions[action_name] = (
                self._site_action(site),
                action_name,
                f"Spočítat rozúčtování za vybraná období – jen {site}",
            )
        return actions

    def _site_action(self, site):
        def action(modeladmin, request, queryset):
            modeladmin._spocitat_rozuctovani(request, queryset, site=site)
        return action

    @admin.action(description="Spočítat rozúčtování za vybraná období (všechny areály)")
    def spocitat_rozuctovani(self, request, queryset):
        self._spocitat_rozuctovani(request, queryset, site=None)

    def _spocitat_rozuctovani(self, request, queryset, site=None):
        from billing.engine import BillingPeriodClosedError, calculate_period, sync_card_activity

        for period in queryset:
            label = f"{period} / {site}" if site else str(period)

            sync_results = sync_card_activity(period, site=site)
            for level, text in sync_results:
                self.message_user(
                    request, f"{label}: {text}",
                    level=messages.SUCCESS if level == "success" else messages.WARNING,
                )

            try:
                result = calculate_period(period, site=site)
            except BillingPeriodClosedError as e:
                self.message_user(request, str(e), level=messages.ERROR)
                continue
            self.message_user(
                request, f"{label}: vytvořeno {result['created']} vyúčtovaných položek.",
                level=messages.SUCCESS,
            )
            # Kazde varovani zvlast (ne spojene do jednoho dlouheho radku
            # pres " | ") - v adminu se v jednom dlouhem bloku spatne
            # hleda, co presne je problem (viz konverzace s Danielem).
            for warning in result["warnings"]:
                self.message_user(request, f"{label}: {warning}", level=messages.WARNING)

    @admin.action(description="Zkontrolovat, co je potřeba zadat (Náklady/Ceník)")
    def zkontrolovat_co_zadat(self, request, queryset):
        """Pro vybraná Období projde vsechny polozky zasobniku a nahlasi:
        - polozky bez Nakladu za obdobi (CostEntry) A bez Vychozi mesicni
          castky (ServicePoolItem.default_amount_czk) - takove polozky
          billing/engine.py potichu preskoci, castka za ne nikomu nepadne
        - merene polozky, ktere maji zadane jednotky, ale nemaji zadnou
          platnou cenu v Ceniku (ani starsi) - spadnou na varovani pri
          samotnem prepoctu

        Sezonni polozky (napr. "odklizeni snehu") se NEROZLISUJI - v
        mesicich bez nakladu se objevi jako "chybi" i kdyz je to spravne,
        Daniel si to vyhodnoti sam (viz konverzace)."""
        for period in queryset:
            missing_cost = []
            missing_price = []
            stale_price = []
            spatna_cena = []

            for item in pronajimatele.omez(
                    ServicePoolItem.objects, "site", request).select_related("site"):
                item_costs = list(CostEntry.objects.filter(service_item=item, period=period))
                if not item_costs:
                    if item.default_amount_czk is None:
                        missing_cost.append(item)
                    continue

                # Cenik je potreba jen u faktur zadanych v jednotkach, ktere
                # nemaji vlastni cenu primo na sobe.
                if not any(
                    ce.amount_czk is None and ce.amount_units is not None
                    and ce.price_per_unit is None
                    for ce in item_costs
                ):
                    continue

                price_entry = (
                    PriceList.objects.filter(service_item=item)
                    .filter(
                        Q(period__year__lt=period.year)
                        | Q(period__year=period.year, period__month__lte=period.month)
                    )
                    .order_by("-period__year", "-period__month")
                    .first()
                )
                mimo = CostEntry.cenik_mimo(item, period, entries=item_costs)
                if mimo:
                    spatna_cena.append((item, mimo))

                if price_entry is None:
                    missing_price.append(item)
                elif price_entry.period_id != period.id:
                    age_months = (
                        (period.year - price_entry.period.year) * 12
                        + (period.month - price_entry.period.month)
                    )
                    stale_price.append((item, price_entry.period, age_months))

            label = str(period)
            if missing_cost:
                names = ", ".join(str(i) for i in missing_cost)
                self.message_user(
                    request,
                    f"{label}: chybí Náklad za období (a nemá Výchozí částku) - nebude se počítat: {names}",
                    level=messages.WARNING,
                )
            if missing_price:
                names = ", ".join(str(i) for i in missing_price)
                self.message_user(
                    request,
                    f"{label}: má zadané jednotky, ale chybí jakákoliv cena v Ceníku: {names}",
                    level=messages.WARNING,
                )
            for item, text in spatna_cena:
                self.message_user(
                    request, f"{label}: {item} - {text}", level=messages.ERROR,
                )
            if stale_price:
                text = "; ".join(
                    f"{item} (cena naposledy nastavena {price_period}, {age} měs. zpět)"
                    for item, price_period, age in stale_price
                )
                self.message_user(
                    request, f"{label}: platné ceny z dřívějška - zkontroluj, jestli se nezměnily: {text}",
                    level=messages.INFO,
                )
            if not (missing_cost or missing_price or stale_price or spatna_cena):
                self.message_user(
                    request, f"{label}: vše zadané, nic nechybí.", level=messages.SUCCESS
                )

    @admin.action(description="Dotáhnout fakturovaná množství do přívodních měřidel")
    def dotahnout_fakturovana_mnozstvi(self, request, queryset):
        """Prepise Fakturovane mnozstvi z Nakladu do Privodnich meridel
        odbernych mist, aby se "dodáno" v reportu Spotřeby měřidel
        nemuselo zadavat dvakrat. Bere jen z polozky, kterou ma odberne
        misto vyslovene nastavenou (SupplyPoint.cost_item) - hadat ji
        podle arealu a tridy nejde, viz help_text toho pole. Sdili logiku
        s prikazem dotahnout_fakturovana_mnozstvi. Viz konverzace
        s Danielem 2026-08-16."""
        from core.management.commands.dotahnout_fakturovana_mnozstvi import dotahnout

        for period in queryset:
            radky = dotahnout(period, write=True)
            if not radky:
                self.message_user(
                    request,
                    f"{period}: žádné odběrné místo nemá vyplněný „Náklad, ze kterého "
                    f"brát fakturované množství“.",
                    messages.WARNING,
                )
                continue
            zapsano = [r for r in radky if r["stav"].startswith(("zapsat", "přepsat"))]
            preskoceno = [r for r in radky if not r["stav"].startswith(("zapsat", "přepsat", "sedí"))]
            if zapsano:
                self.message_user(
                    request,
                    f"{period}: doplněno " + ", ".join(
                        f"{r['meter'].code} = {r['hodnota']}" for r in zapsano
                    ),
                    messages.SUCCESS,
                )
            else:
                self.message_user(request, f"{period}: nebylo co doplnit.", messages.INFO)
            for r in preskoceno:
                self.message_user(
                    request, f"{period}: {r['meter'].code} - {r['stav']}", messages.WARNING
                )

    @admin.action(description="Vygenerovat chybějící Náklady za období (prázdné, k doplnění)")
    def vygenerovat_chybejici_naklady(self, request, queryset):
        """Pro vybrana Obdobi vytvori PRAZDNY CostEntry (bez amount_units
        i amount_czk, jen s poznamkou 'K DOPLNĚNÍ') pro kazdou polozku,
        ktera pro dane obdobi zadny CostEntry nema a nema ani Vychozi
        mesicni castku - aby je Daniel nemusel zakladat rucne jednu po
        druhe pres "Pridat", jen dohledat v seznamu Nakladu (vyhledavani
        podle poznamky) a doplnit realna cisla.

        ZAMERNE se nevyplnuje amount_czk=0 (i kdyz o to Daniel puvodne
        zadal) - prazdny CostEntry porad spadne na varovani "chybí cena/
        náklad" pri "Spočítat rozúčtování" (billing/engine.py), takze
        zapomenuty/nedoplneny radek nikdy tise neuctuje 0 Kc. Kdyby mel
        amount_czk rovnou 0, engine by to vzal jako platnou nulovou
        castku BEZ JAKEHOKOLIV varovani - to by bylo nebezpecnejsi nez
        zadny CostEntry vubec."""
        for period in queryset:
            created = []
            for item in pronajimatele.omez(ServicePoolItem.objects, "site", request):
                if item.default_amount_czk is not None:
                    continue
                # Uz aspon jednu fakturu ma - dalsi (od jineho dodavatele) si
                # Daniel prida sam, generovat prazdne stuby by je jen mnozilo.
                if CostEntry.objects.filter(service_item=item, period=period).exists():
                    continue
                CostEntry.objects.create(service_item=item, period=period, note=CostEntry.NOTE_K_DOPLNENI)
                created.append(item)

            label = str(period)
            if created:
                names = ", ".join(str(i) for i in created)
                self.message_user(
                    request,
                    f"{label}: vytvořeno {len(created)} prázdných Nákladů (poznámka „{CostEntry.NOTE_K_DOPLNENI}“) - "
                    f"doplň částky v seznamu Náklady za období (vyhledej „{CostEntry.NOTE_K_DOPLNENI}“): {names}",
                    level=messages.WARNING,
                )
            else:
                self.message_user(
                    request, f"{label}: nic k vygenerování, vše už existuje nebo má Výchozí částku.",
                    level=messages.SUCCESS,
                )

    @admin.action(description="Uzavřít vybraná období (zamkne proti přepočtu)")
    def uzavrit_obdobi(self, request, queryset):
        updated = queryset.update(status=Period.Status.CLOSED)
        self.message_user(
            request, f"Uzavřeno {updated} období - rozúčtování už nepůjde přepočítat.", level=messages.SUCCESS
        )

    @admin.action(description="Znovu otevřít vybraná období")
    def znovu_otevrit_obdobi(self, request, queryset):
        updated = queryset.update(status=Period.Status.OPEN)
        self.message_user(
            request, f"Znovu otevřeno {updated} období - rozúčtování teď jde přepočítat.", level=messages.WARNING
        )


@admin.register(InvoiceClassColor)
class InvoiceClassColorAdmin(ModelAdmin):
    """Trida je JEDINY seznam, do ktereho se radi Polozky zasobniku,
    Meridla i Odberna mista (drive na to byly dva nezavisle vycty, viz
    docstring modelu). Radky jdou pridavat, prejmenovat i mazat.

    Mazani je blokovane jen kdyz Tridu jeste neco pouziva - osirel by na
    tom neplatny kod (neni to FK, jen text). Drive se navic nesmely mazat
    ctyri zakladni Tridy, protoze na nich visely napevno zapsane sekce v
    Karte klienta; ted se sekce generuji z Trid, takze po smazani proste
    zmizi i sekce."""

    list_display = (
        "nazev", "default_unit_of_measure", "sort_order",
        "ma_sekci_klicu", "deduct_fixed_from_pool", "pocet_pouziti",
        "color_light", "color_dark", "text_color_light", "text_color_dark",
    )
    list_editable = (
        "default_unit_of_measure", "sort_order", "ma_sekci_klicu", "deduct_fixed_from_pool",
    )
    ordering = ("sort_order", "invoice_class")

    @display(description="Název", ordering="label")
    def nazev(self, obj):
        """Obarveno podle Tridy - drive to delal samostatny sloupec
        "Ukázka", ted uz je redundantni, protoze Nazev nese totez."""
        return colored_by_class(obj.label or obj.invoice_class, obj.invoice_class)

    @display(description="Použito u")
    def pocet_pouziti(self, obj):
        casti = []
        for model, popis in (
            (ServicePoolItem.objects.filter(invoice_class=obj.invoice_class), "položek"),
            (Meter.objects.filter(meter_type=obj.invoice_class), "měřidel"),
            (SupplyPoint.objects.filter(meter_type=obj.invoice_class), "odběrných míst"),
        ):
            pocet = model.count()
            if pocet:
                casti.append(f"{pocet} {popis}")
        return " + ".join(casti) if casti else "—"

    def get_readonly_fields(self, request, obj=None):
        """Kod jde zadat jen pri zalozeni - zmena existujiciho by odpojila
        Polozky/Meridla/Odberna mista, ktera na nej odkazuji obycejnym
        textem (neni to FK). Prejmenovat jde Nazev, ten je jen na
        zobrazeni."""
        if obj is not None:
            return ("invoice_class",)
        return ()

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return True
        return not (
            ServicePoolItem.objects.filter(invoice_class=obj.invoice_class).exists()
            or Meter.objects.filter(meter_type=obj.invoice_class).exists()
            or SupplyPoint.objects.filter(meter_type=obj.invoice_class).exists()
        )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name in (
            "color_light", "color_dark", "text_color_light", "text_color_dark",
        ):
            from unfold.widgets import UnfoldAdminColorInputWidget
            formfield.widget = UnfoldAdminColorInputWidget()
        return formfield


@admin.register(InflationRate)
class InflationRateAdmin(ModelAdmin):
    list_display = ("year", "percent")
    ordering = ("-year",)
    list_per_page = 10
    list_after_template = "admin/core/inflationrate/chart.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(self._chart_context())
        return super().changelist_view(request, extra_context)

    def _chart_context(self):
        """SVG sloupcovy graf vyvoje miry inflace po letech, vykreslovany
        pod tabulkou na zmenovnem seznamu (list_after_template - podpora
        primo v Unfoldu, viz change_list.html). Geometrie se pocita tady
        v Pythonu, stejny vzor jako report_grafy_trid_view."""
        import math
        from decimal import Decimal

        rates = list(InflationRate.objects.order_by("year"))
        if not rates:
            return {"inflation_chart_bars": None}

        max_value = max(r.percent for r in rates)

        def _nice_ceiling(value):
            value = float(value)
            if value <= 0:
                return Decimal("1")
            exp = math.floor(math.log10(value))
            base = value / (10 ** exp)
            nice = 1 if base <= 1 else 2 if base <= 2 else 5 if base <= 5 else 10
            return Decimal(str(nice)) * (Decimal("10") ** exp)

        y_max = _nice_ceiling(max_value)

        plot_h = 220
        bar_w = 20
        bar_gap = 6
        left_margin = 48
        top_margin = 24
        bottom_margin = 40
        chart_w = left_margin + len(rates) * (bar_w + bar_gap) + bar_gap
        chart_h = top_margin + plot_h + bottom_margin
        baseline_y = top_margin + plot_h

        def _y(value):
            if y_max == 0:
                return baseline_y
            return float(baseline_y - (value / y_max) * plot_h)

        gridlines = []
        for i in range(5):
            frac = Decimal(i) / Decimal(4)
            value = y_max * frac
            gy = _y(value)
            gridlines.append({
                "y": gy, "label_x": left_margin - 8, "label_y": gy + 4,
                "label": f"{value:.1f} %",
            })

        bars = []
        x = left_margin + bar_gap
        for r in rates:
            bar_top = _y(r.percent)
            label_x = x + bar_w / 2
            bars.append({
                "x": x, "y": bar_top, "w": bar_w, "h": max(baseline_y - bar_top, 0),
                "year": r.year, "value": r.percent,
                "label_x": label_x,
                "year_label_y": baseline_y + 14,
                "is_peak": r.percent == max_value,
                "peak_label_y": bar_top - 6,
            })
            x += bar_w + bar_gap

        return {
            "inflation_chart_bars": bars,
            "inflation_chart_gridlines": gridlines,
            "inflation_chart_w": chart_w,
            "inflation_chart_h": chart_h,
            "inflation_chart_baseline_y": baseline_y,
            "inflation_chart_left_margin": left_margin,
        }


@admin.register(SupplyPoint)
class SupplyPointAdmin(PodlePronajimatele, ModelAdmin):
    cesta_k_arealu = "site"
    list_display = ("name_colored", "code", "site", "meter_type", "main_meter", "legal_loss_pct", "member_count")
    list_select_related = ("site", "main_meter")
    list_filter = ("site", "meter_type")
    search_fields = ("name", "code")
    autocomplete_fields = ("main_meter", "cost_item")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "meter_type":
            return invoice_class_choice_field(db_field)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @display(description="Název", ordering="name")
    def name_colored(self, obj):
        return colored_by_meter_type(obj.name, obj.meter_type)

    fieldsets = (
        (None, {
            "fields": (
                ("site", "meter_type"),
                ("name", "code"),
                "main_meter",
                "cost_item",
                "legal_loss_pct",
                "note",
            ),
            "description": (
                "Odběrné místo = fyzický přípojný bod (EAN), pod který spadá víc "
                "podružných měřidel. 'Přívodní měřidlo' je to, jehož spotřeba = kolik "
                "do odběru celkem došlo (např. 668_CELKEM); nech prázdné, pokud se "
                "dodané množství bere jen z faktury. Členská měřidla se přiřazují na "
                "samotném Měřidle (pole 'Odběrné místo') nebo hromadnou akcí v seznamu měřidel."
            ),
        }),
    )

    def get_queryset(self, request):
        """Pocet clenskych meridel se pocita v databazi jednim dotazem.

        Driv to bylo obj.member_meters.count() ve sloupci, tedy jeden
        dotaz na KAZDY radek seznamu. Daniel 2026-08-26."""
        from django.db.models import Count

        return super().get_queryset(request).annotate(
            pocet_meridel=Count("member_meters", distinct=True)
        )

    @display(description="Počet měřidel", ordering="pocet_meridel")
    def member_count(self, obj):
        """Odkaz do seznamu Meridel omezeneho na tohle odberne misto -
        aby slo z prehledu rovnou videt, co pod nej spada. Filtr
        supply_point uz MeterAdmin.list_filter ma, takze staci adresa.
        Nula se nelinkuje, nebylo by co ukazat. Daniel 2026-08-26."""
        from django.urls import reverse
        from django.utils.html import format_html

        pocet = getattr(obj, "pocet_meridel", None)
        if pocet is None:
            pocet = obj.member_meters.count()
        if not pocet:
            return pocet
        adresa = "%s?supply_point__id__exact=%s" % (
            reverse("admin:core_meter_changelist"), obj.pk,
        )
        return format_html(
            '<a href="{}" title="Ukázat měřidla tohoto odběrného místa">{}</a>',
            adresa, pocet,
        )


class _MaFotoFilter(admin.SimpleListFilter):
    """Filtr "ma fotku" - hlavne kvuli dohledani odectu, ke kterym
    fotka chybi. Daniel 2026-09-01."""

    title = "Foto odečtu"
    parameter_name = "ma_foto"

    def lookups(self, request, model_admin):
        return (("1", "s fotkou"), ("0", "bez fotky"))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.exclude(photo="").exclude(photo__isnull=True)
        if self.value() == "0":
            return queryset.filter(Q(photo="") | Q(photo__isnull=True))
        return queryset


@admin.register(ReadingsClosure)
class ReadingsClosureAdmin(PodlePronajimatele, ModelAdmin):
    """Uzavreni odectu - hlavne proto, aby ho admin mohl ZRUSIT.

    Zaklada ho spravce tlacitkem na obrazovce odectu; smazanim zaznamu se
    odecty zase odemknou. Daniel 2026-09-01."""

    cesta_k_arealu = "site"
    list_display = ("period", "site", "closed_at", "closed_by", "note")
    list_select_related = ("period", "site", "closed_by")
    list_filter = ("period", "site")
    readonly_fields = ("closed_at", "closed_by")


@admin.register(MeterReading)
class MeterReadingAdmin(PodlePronajimatele, DefaultToCurrentPeriodMixin, ModelAdmin):
    cesta_k_arealu = "meter__site"
    list_display = ("meter_colored", "period", "reading_date", "value", "reset_from_value",
                    "ma_foto", "created_by")
    list_select_related = ("meter", "period")
    list_filter = ("meter__site", "meter__meter_type", "period", _PeriodDefaultMarkerFilter,
                   _MaFotoFilter)
    search_fields = ("meter__code", "meter__name")
    autocomplete_fields = ("meter",)
    readonly_fields = ("created_by",)

    @display(description="Foto", boolean=True, ordering="photo")
    def ma_foto(self, obj):
        """Jestli u odectu visi fotka. Cte se primo z radku (pole photo),
        takze zadny dotaz navic - na R2 se nesaha, jen se kouka, jestli je
        vyplnene jmeno souboru. Daniel 2026-09-01."""
        return bool(obj.photo)

    def save_model(self, request, obj, form, change):
        """Kdo odecet zapsal - vyplni se jen pri zalozeni.

        Pri pozdejsi uprave se puvodni autor nepresepisuje: zajima nas,
        kdo stav odecetl, ne kdo naposledy opravil preklep.
        Viz Daniel 2026-09-01."""
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    ordering = ("meter__code", "-period")

    @display(description="Měřidlo", ordering="meter__code")
    def meter_colored(self, obj):
        return colored_by_meter_type(str(obj.meter), obj.meter.meter_type)


def _jednotka_polozky(item):
    """Merna jednotka polozky Zasobniku - u merenych polozek podle
    napojeneho meridla, u nemerenych (Ostatni) se uctuje vzdy primo v Kc."""
    if item.meter_id:
        return item.meter.unit_of_measure or "-"
    return "Kč"


def _format_kc(value, decimals=2):
    """Cesky format meny: '1 234,50 Kč' (mezera jako oddelovac tisicu,
    carka jako desetinny oddelovac). Zarovnano vpravo (blokovy text-align)
    - v CR se castky v tabulkach zarovnavaji vpravo, ne vlevo jako
    bezny text, viz konverzace s Danielem 2026-08-12. white-space:nowrap,
    aby se castka v uzsim sloupci nezalamovala na dva radky (viz
    konverzace s Danielem) - sloupec se pak sam roztahne podle obsahu."""
    from django.utils.html import format_html

    style = "display:block; text-align:right; white-space:nowrap;"
    if value is None:
        return format_html('<span style="{}">-</span>', style)
    text = f"{value:,.{decimals}f}"
    text = text.replace(",", "\x00").replace(".", ",").replace("\x00", " ")
    return format_html('<span style="{}">{} Kč</span>', style, text)


def _efektivni_cena_za_jednotku(cost_entry):
    """Efektivni cena za jednotku pro CostEntry - primo z amount_czk/
    amount_units, pripadne (u merenych polozek bez primo zadaneho
    amount_czk) z aktualne platneho Ceniku pro dane obdobi."""
    if cost_entry.amount_units:
        if cost_entry.amount_czk is not None:
            try:
                return cost_entry.amount_czk / cost_entry.amount_units
            except ZeroDivisionError:
                pass
        return PriceList.get_price_for_period(cost_entry.service_item, cost_entry.period)
    return None


@admin.register(ServicePoolItem)
class ServicePoolItemAdmin(PodlePronajimatele, ModelAdmin):
    cesta_k_arealu = "site"
    list_display = (
        "name", "site", "invoice_class", "unit", "meter", "jednotka",
        "default_allocation_type", "default_amount_czk_display", "weight_unit_label",
    )
    list_select_related = ("site", "unit", "meter")
    list_filter = ("site", "invoice_class")
    search_fields = ("name",)
    autocomplete_fields = ("unit", "meter")
    readonly_fields = ("meridla_prehled",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "invoice_class":
            return invoice_class_choice_field(db_field)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Jednotka")
    def jednotka(self, obj):
        return _jednotka_polozky(obj)

    @admin.display(description="Měřidla u této položky")
    def meridla_prehled(self, obj):
        """Neni to skutecny Django inline (Meter nema primou FK na
        ServicePoolItem, jen neprimo pres AllocationKey.meter) - misto
        toho readonly pole na formulari s deduplikovanym seznamem vsech
        meridel, ktera se u polozky pouzivaji (hlavni meridlo + vse
        napojene pres klice), vc. jejich "Co je vahou" popisku."""
        if obj is None or obj.pk is None:
            return "(uloží se po prvním uložení záznamu)"
        from django.utils.html import format_html, format_html_join

        meters = {}
        if obj.meter_id:
            meters[obj.meter_id] = (obj.meter, "hlavní měřidlo položky")
        for key in obj.allocation_keys.select_related("meter").filter(meter__isnull=False):
            if key.meter_id not in meters:
                meters[key.meter_id] = (key.meter, "napojené přes klíč")

        if not meters:
            return "—"

        rows = format_html_join(
            "", "<li>{} — {} ({}){}{}</li>",
            (
                (
                    m.code or m.name, m.get_meter_type_display(), role,
                    f", {m.unit_of_measure}" if m.unit_of_measure else "",
                    f" · Co je váhou: {m.weight_unit_label}" if m.weight_unit_label else "",
                )
                for m, role in sorted(meters.values(), key=lambda t: (t[0].code or t[0].name))
            ),
        )
        return format_html("<ul style='margin:0;padding-left:16px;'>{}</ul>", rows)

    @admin.display(description="Výchozí měsíční částka (Kč)", ordering="default_amount_czk")
    def default_amount_czk_display(self, obj):
        return _format_kc(obj.default_amount_czk)

    def get_urls(self):
        from django.urls import path
        from django.http import JsonResponse

        def class_lookup(request, item_id):
            # Kontext pronajimatele - viz komentar u area_lookup.
            data = (
                self.get_queryset(request).filter(pk=item_id)
                .values("invoice_class", "default_allocation_type")
                .first()
            )
            return JsonResponse(data or {"invoice_class": None, "default_allocation_type": None})

        urls = super().get_urls()
        custom = [
            path(
                "class-lookup/<int:item_id>/",
                self.admin_site.admin_view(class_lookup),
                name="core_servicepoolitem_class_lookup",
            ),
            path(
                "search/",
                self.admin_site.admin_view(self.service_item_search),
                name="core_servicepoolitem_search",
            ),
        ]
        return custom + urls

    def service_item_search(self, request):
        from django.http import JsonResponse
        from django.db.models import Q

        term = request.GET.get("term", "").strip()
        site_id = request.GET.get("site_id")
        invoice_class = request.GET.get("invoice_class")

        qs = pronajimatele.omez(ServicePoolItem.objects, "site", request)
        if site_id:
            qs = qs.filter(site_id=site_id)
        if invoice_class:
            qs = qs.filter(invoice_class=invoice_class)
        if term:
            qs = qs.filter(Q(name__icontains=term))

        qs = qs.order_by("name")[:50]
        return JsonResponse({"results": [{"id": i.id, "text": str(i)} for i in qs]})


@admin.register(AllocationKey)
class AllocationKeyAdmin(PodlePronajimatele, ModelAdmin):
    cesta_k_arealu = "service_item__site"
    list_display = (
        "client_card_display", "service_item", "allocation_type", "value_display",
        "meter", "unit", "deduct_from_pool", "is_billed", "valid_from", "valid_to",
    )
    list_select_related = ("client_card", "client_card__client", "service_item", "service_item__site", "meter", "unit")
    list_filter = ("allocation_type", "deduct_from_pool", "is_billed")
    search_fields = ("meter__code", "meter__name", "client_card__client__name", "service_item__name")
    autocomplete_fields = ("client_card", "service_item", "meter", "unit")
    actions = ["deduct_from_pool_on", "deduct_from_pool_off"]

    @admin.action(description="Zapnout 'Odečíst z celkového nákladu'")
    def deduct_from_pool_on(self, request, queryset):
        n = queryset.update(deduct_from_pool=True)
        self.message_user(
            request,
            f"Zapnuto 'Odečíst z celkového nákladu' u {n} klíčů "
            f"(uplatní se jen u typů Pevná částka / Dle výměry).",
            messages.SUCCESS,
        )

    @admin.action(description="Vypnout 'Odečíst z celkového nákladu' (paušál se neodečte)")
    def deduct_from_pool_off(self, request, queryset):
        n = queryset.update(deduct_from_pool=False)
        self.message_user(
            request,
            f"Vypnuto u {n} klíčů - paušál se pak NEodečte od nákladu a "
            f"celý náklad se rozpočítá ostatním kartám.",
            messages.WARNING,
        )

    @admin.display(description="Karta klienta", ordering="client_card")
    def client_card_display(self, obj):
        return obj.client_card.description or f"Karta {obj.client_card.client}"

    @admin.display(description="Hodnota", ordering="value")
    def value_display(self, obj):
        # Vyznam pole "value" zavisi na typu klice - jen u Pevne castky jde
        # skutecne o Kc, u Plocha x cena/m2 jde o m2, u ostatnich o vahu/procento.
        if obj.allocation_type == AllocationKey.AllocationType.FIXED_AMOUNT:
            return _format_kc(obj.value)
        if obj.allocation_type == AllocationKey.AllocationType.AREA_PRICE:
            return "-" if obj.value is None else f"{obj.value} m²"
        if obj.allocation_type == AllocationKey.AllocationType.WEIGHTED_COUNT and obj.weight_unit_label:
            return f"{obj.value} ({obj.weight_unit_label})"
        return obj.value


@admin.register(PriceList)
class PriceListAdmin(PodlePronajimatele, DefaultToCurrentPeriodMixin, ModelAdmin):
    cesta_k_arealu = "service_item__site"
    list_display = ("service_item_colored", "period", "price_per_unit_display", "note")
    list_select_related = ("service_item", "service_item__site", "period")
    list_filter = ("period", "service_item__site", _PeriodDefaultMarkerFilter)
    autocomplete_fields = ("service_item",)
    search_fields = ("service_item__name",)
    list_after_template = "admin/core/pricelist/inherited_prices.html"

    @display(description="Položka", ordering="service_item__name")
    def service_item_colored(self, obj):
        return colored_by_class(str(obj.service_item), obj.service_item.invoice_class)

    @admin.display(description="Cena za jednotku (Kč)", ordering="price_per_unit")
    def price_per_unit_display(self, obj):
        return _format_kc(obj.price_per_unit, decimals=4)

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom = [
            path(
                "prevzit/<int:pricelist_id>/<int:period_id>/",
                self.admin_site.admin_view(self.prevzit_do_obdobi),
                name="core_pricelist_prevzit",
            ),
        ]
        return custom + urls

    def prevzit_do_obdobi(self, request, pricelist_id, period_id):
        """Zalozi pro vybrane Obdobi vlastni zaznam v Ceniku se stejnou
        cenou, jaka se do nej dosud prebirala z drivejska - aby slo cenu
        "zhmotnit" a pak upravit, bez rucniho prepisovani. Viz konverzace
        s Danielem 2026-08-16.

        Zmena dat = jen POST (GET by sel vyvolat i obyc. odkazem)."""
        from django.core.exceptions import ValidationError
        from django.shortcuts import redirect
        from django.urls import reverse

        redirect_to = (
            request.META.get("HTTP_REFERER")
            or reverse("admin:core_pricelist_changelist")
        )
        if request.method != "POST":
            return redirect(redirect_to)

        # Kontext pronajimatele - bez nej slo prostym ID v adrese prevzit
        # cenu z ceniku cizniho pronajimatele. Daniel 2026-08-25.
        source = (self.get_queryset(request)
                  .filter(pk=pricelist_id).select_related("service_item").first())
        period = Period.objects.filter(pk=period_id).first()
        if source is None or period is None:
            self.message_user(request, "Zdrojová cena nebo období už neexistuje.", messages.ERROR)
            return redirect(redirect_to)

        if PriceList.objects.filter(service_item=source.service_item, period=period).exists():
            self.message_user(
                request,
                f"{source.service_item} už pro {period} vlastní cenu má.",
                messages.WARNING,
            )
            return redirect(redirect_to)

        new = PriceList(
            service_item=source.service_item, period=period,
            price_per_unit=source.price_per_unit,
            note=f"Převzato z období {source.period}",
        )
        try:
            new.full_clean()
        except ValidationError as exc:
            # Typicky uzavrene obdobi (PriceList.clean) - radeji hlaska nez 500.
            self.message_user(request, "; ".join(exc.messages), messages.ERROR)
            return redirect(redirect_to)
        new.save()
        self.message_user(
            request,
            f"{source.service_item}: cena {source.price_per_unit} převzata z {source.period} do {period}.",
            messages.SUCCESS,
        )
        return redirect(redirect_to)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["inherited_price_rows"] = self._inherited_price_rows(request)
        return super().changelist_view(request, extra_context)

    def _inherited_price_rows(self, request):
        """Ceny, ktere ve vybranem Obdobi PLATI, ale nemaji tu vlastni
        zaznam - PriceList.get_price_for_period bere posledni cenu k datu,
        takze polozka bez zaznamu v 07/2026 dal jede za cenu z 06/2026.
        V seznamu filtrovanem na 07/2026 pak nebylo videt vubec nic a
        vypadalo to, ze ceny chybi. Viz konverzace s Danielem 2026-08-16.

        Vraci i obdobi, ze ktereho se cena prebira, aby slo poznat, jak
        je stara."""
        from django.urls import reverse

        period_id = request.GET.get("period__id__exact")
        if not period_id:
            return None
        period = Period.objects.filter(pk=period_id).first()
        if period is None:
            return None

        own_item_ids = set(
            PriceList.objects.filter(period=period).values_list("service_item_id", flat=True)
        )
        earlier = (
            pronajimatele.omez(PriceList.objects, "service_item__site", request)
            .filter(
                Q(period__year__lt=period.year)
                | Q(period__year=period.year, period__month__lt=period.month)
            )
            .exclude(service_item_id__in=own_item_ids)
            .select_related("service_item", "service_item__site", "period")
            .order_by("service_item_id", "-period__year", "-period__month")
        )
        site_id = request.GET.get("service_item__site__id__exact")
        if site_id:
            earlier = earlier.filter(service_item__site_id=site_id)

        # Za kazdou polozku jen NEJNOVEJSI drivejsi cena - stejne pravidlo
        # jako get_price_for_period (razeni vyse to zaridi, staci vzit
        # prvni vyskyt).
        seen = set()
        rows = []
        for pl in earlier:
            if pl.service_item_id in seen:
                continue
            seen.add(pl.service_item_id)
            rows.append({
                "item": pl.service_item,
                "trida": colored_by_class(
                    pl.service_item.get_invoice_class_display(), pl.service_item.invoice_class
                ),
                "price_html": _format_kc(pl.price_per_unit, decimals=4),
                "from_period": pl.period,
                "pk": pl.pk,
                "prevzit_url": reverse(
                    "admin:core_pricelist_prevzit", args=[pl.pk, period.pk]
                ),
            })
        rows.sort(key=lambda r: (r["item"].invoice_class, r["item"].site.name, r["item"].name))
        return {"period": period, "rows": rows}


class CostEntryVyplnenoFilter(admin.SimpleListFilter):
    """Filtr 'Stav' v seznamu Nakladu za obdobi - 'Nevyplneno' ukaze jen
    zaznamy bez amount_units i bez amount_czk (typicky prazdne stuby
    z akce "Vygenerovat chybějící Náklady", poznamka 'K DOPLNĚNÍ') - aby
    Daniel nemusel psat hledani rucne a nemusel proklikavat uz hotove
    polozky (viz konverzace - "Pult ochrany ALSYKO" priklad polozky,
    ktera uz je vyplnena a nema co delat v seznamu k doplneni)."""
    title = "stav"
    parameter_name = "stav"

    def lookups(self, request, model_admin):
        return (("nevyplneno", "Nevyplněno"), ("vyplneno", "Vyplněno"))

    def queryset(self, request, queryset):
        if self.value() == "nevyplneno":
            return queryset.filter(amount_units__isnull=True, amount_czk__isnull=True)
        if self.value() == "vyplneno":
            return queryset.exclude(amount_units__isnull=True, amount_czk__isnull=True)
        return queryset


@admin.register(CostEntry)
class CostEntryAdmin(PodlePronajimatele, DefaultToCurrentPeriodMixin, ModelAdmin):
    """list_editable u amount_units/amount_czk - primo v seznamu (po
    filtru na Obdobi) jde zadat cisla u vice polozek najednou a ulozit
    jednim tlacitkem, misto otevirani kazdeho zaznamu zvlast. Kvuli tomu
    (Django to vyzaduje) je list_display_links presunuty na service_item,
    aby zustal jasny "odkazovaci" sloupec pro otevreni celeho formulare
    (napr. kvuli kontrolnim polim). Poznamka se v seznamu nezobrazuje
    (jen ve formulari zaznamu) - viz konverzace s Danielem."""
    cesta_k_arealu = "service_item__site"

    list_display = (
        "trida", "service_item", "supplier", "period", "amount_units", "amount_czk",
        "jednotka", "kc_za_jednotku", "amount_czk_display",
    )
    list_select_related = ("service_item", "service_item__meter", "service_item__site", "period")
    list_display_links = ("service_item",)
    list_editable = ("amount_units", "amount_czk")
    list_filter = (
        CostEntryVyplnenoFilter, "period", "service_item__invoice_class", "service_item__site",
        _PeriodDefaultMarkerFilter,
    )
    search_fields = ("note", "service_item__name")
    list_after_template = "admin/core/costentry/default_amount_items.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["default_amount_rows"] = self._default_amount_rows(request)
        return super().changelist_view(request, extra_context)

    def _default_amount_rows(self, request):
        """Polozky, ktere pro vybrane Obdobi NEMAJI zadny Naklad (CostEntry),
        ale presto se do vyuctovani pocitaji - pres jejich Vychozi castku
        (ServicePoolItem.default_amount_czk), viz billing/engine.py
        calculate_period (elif service_item.default_amount_czk is not
        None). Bez tohohle by v seznamu Nakladu za obdobi tyhle
        "automaticky se opakujici" polozky vubec nebyly videt - Daniel
        chce videt VSECHNY naklady vazane k obdobi, i kdyz se kazdy
        mesic nevyplnuji (viz konverzace s Danielem)."""
        period_id = request.GET.get("period__id__exact")
        if not period_id:
            return None
        period = Period.objects.filter(pk=period_id).first()
        if period is None:
            return None

        items = pronajimatele.omez(
            ServicePoolItem.objects.exclude(default_amount_czk__isnull=True),
            "site", request,
        ).select_related("site")
        site_id = request.GET.get("service_item__site__id__exact")
        if site_id:
            items = items.filter(site_id=site_id)
        invoice_class = request.GET.get("service_item__invoice_class__exact")
        if invoice_class:
            items = items.filter(invoice_class=invoice_class)
        items = items.exclude(cost_entries__period=period).order_by("invoice_class", "site__name", "name")

        class_labels = InvoiceClassColor.label_map()
        rows = [
            {
                "trida": class_labels[item.invoice_class],
                "item": item,
                "amount_html": _format_kc(item.default_amount_czk),
            }
            for item in items
        ]
        return {"period": period, "rows": rows}

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """amount_units/amount_czk: bezny <input type=number> mel dve
        neduziti vlastnosti - cisla zarovnana vlevo (v CR se castky
        zarovnavaji vpravo) a nechtene sipky nahoru/dolu, ktere u
        nich nedavaji smysl (viz konverzace s Danielem). Sipky jde
        schovat jen pres CSS pseudo-elementy (::-webkit-inner-spin-
        button), coz u type=number vubec nejde bez CSS - proto misto
        toho pouzity Unfoldem vlastni textovy widget
        (UnfoldAdminTextInputWidget) s vyrovnanim vpravo a Kc
        priponou primo pres jeho "suffix" - nativni Unfold funkce,
        zadne vlastni CSS."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name in ("amount_units", "amount_czk"):
            from unfold.widgets import INPUT_CLASSES, UnfoldAdminTextInputWidget
            classes = [*INPUT_CLASSES, "text-right"]
            attrs = {"class": " ".join(classes), "inputmode": "decimal"}
            if db_field.name == "amount_czk":
                # "suffix" (na rozdil od "suffix_icon") sam o sobe
                # nerezervuje misto - napravo je jen absolutne
                # umisteny popisek "Kč" prekryvajici se s pravo
                # zarovnanym textem pole. pr-9 (stejna hodnota, jakou
                # by pouzil Unfold sam pro suffix_icon) mu udela misto.
                attrs["suffix"] = "Kč"
                attrs["class"] += " pr-9"
            formfield.widget = UnfoldAdminTextInputWidget(attrs=attrs)
            formfield.localize = True
        return formfield
    autocomplete_fields = ("service_item",)
    readonly_fields = ("kontrola_cena_za_jednotku", "kontrola_castka_celkem")

    def get_queryset(self, request):
        """Serazeno podle Tridy (ve stejnem poradi jako vsude jinde v appce -
        Najemne/Elektrina/Voda/Teplo/Ostatni, viz ServicePoolItem.InvoiceClass
        a _CLASS_ORDER v billing/statement_generator.py), ne abecedne podle
        kodu tridy - Daniel chce naklady v seznamu videt poseskupovane podle
        typu."""
        from django.db.models import Case, IntegerField, When

        class_order = {code: i for i, (code, _) in enumerate(InvoiceClassColor.choices())}
        whens = [When(service_item__invoice_class=code, then=i) for code, i in class_order.items()]
        qs = super().get_queryset(request)
        return qs.annotate(_trida_poradi=Case(*whens, output_field=IntegerField())).order_by(
            "_trida_poradi", "service_item__site", "service_item__name", "-period__year", "-period__month"
        )

    @admin.display(description="Třída", ordering="service_item__invoice_class")
    def trida(self, obj):
        return colored_by_class(
            obj.service_item.get_invoice_class_display(), obj.service_item.invoice_class
        )

    @admin.display(description="Jednotka")
    def jednotka(self, obj):
        # Jednotka zadana primo na nakladu ma prednost - u polozky s vic
        # fakturami se muzou lisit (pelety v kg vs elektrokotel v kWh).
        return obj.unit_of_measure or _jednotka_polozky(obj.service_item)

    @admin.display(description="Kč/jednotka")
    def kc_za_jednotku(self, obj):
        price = _efektivni_cena_za_jednotku(obj)
        return _format_kc(price, decimals=4)

    @admin.display(description="Částka (Kč)", ordering="amount_czk")
    def amount_czk_display(self, obj):
        return _format_kc(obj.get_amount_czk())

    @admin.display(description="Cena za jednotku (kontrola)")
    def kontrola_cena_za_jednotku(self, obj):
        """Zobrazeno primo ve formulari zaznamu (ne jen ve vypisu) - aby
        bylo pri zadavani nakladu hned videt, jaka cena/jednotku se
        skutecne pouzije (vlastni amount_czk, nebo dopocet z Ceniku),
        bez nutnosti dohledavat to zvlast. Viz konverzace s Danielem -
        chce to vidy pro kontrolu proti fakturovanemu tarifu dodavatele."""
        if obj is None or obj.pk is None:
            return "(uloží se po prvním uložení záznamu)"
        price = _efektivni_cena_za_jednotku(obj)
        return _format_kc(price, decimals=4)

    @admin.display(description="Celková částka (kontrola)")
    def kontrola_castka_celkem(self, obj):
        if obj is None or obj.pk is None:
            return "(uloží se po prvním uložení záznamu)"
        return _format_kc(obj.get_amount_czk())


@admin.register(BillingLine)
class BillingLineAdmin(PodlePronajimatele, DefaultToCurrentPeriodMixin, ModelAdmin):
    cesta_k_arealu = "service_item__site"
    list_display = ("client_card_display", "service_item", "period", "amount_display", "share_display")
    list_select_related = ("client_card", "client_card__client", "service_item", "service_item__site", "period")
    list_filter = ("period", _PeriodDefaultMarkerFilter)
    search_fields = ("client_card__client__name",)
    readonly_fields = ("client_card_display", "period", "service_item", "amount", "share_display", "calc_detail")
    actions = ["generovat_vyuctovani_pdf"]

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path(
                "detail/",
                self.admin_site.admin_view(self.detail_view),
                name="core_billingline_detail",
            ),
            path(
                "detail/klient/<int:client_id>/",
                self.admin_site.admin_view(self.detail_client_view),
                name="core_billingline_detail_client",
            ),
            path(
                "prehled/",
                self.admin_site.admin_view(self.prehled_view),
                name="core_billingline_prehled",
            ),
            path(
                "prehled/meridla/",
                self.admin_site.admin_view(self.prehled_meridla_view),
                name="core_billingline_prehled_meridla",
            ),
            path(
                "podil-vah/",
                self.admin_site.admin_view(self.podil_vah_view),
                name="core_billingline_podil_vah",
            ),
            path(
                "report/grafy-trid/",
                self.admin_site.admin_view(self.report_grafy_trid_view),
                name="core_billingline_report_grafy_trid",
            ),
            path(
                "report/pausalni-klienti/",
                self.admin_site.admin_view(self.report_pausalni_klienti_view),
                name="core_billingline_report_pausalni",
            ),
        ]
        return custom + urls

    def report_pausalni_klienti_view(self, request):
        """Report (Reporty v menu): pro KARTY, ktere maji sluzby/energie
        zahrnute rovnou v najmu (aspon jeden BillingLine.is_billed=False
        v danem obdobi), ukaze po Obdobich za AKTUALNI rok:
        - Naklad: soucet jejich is_billed=False radku (co by je stalo
          sluzby, kdyby se fakturovaly zvlast)
        - Vynos: SKUTECNY najem karty (CardUnit.monthly_rent, stejny
          vypocet jako "Přehled nájemného" vc. zaokrouhleni nahoru) -
          PUVODNE se tu scital soucet is_billed=True radku, coz davalo
          nesmyslne cislo (napr. u CALAMARI SE se takhle zapocitaly
          jeji VLASTNI energie na FM, misto najmu - is_billed=False bylo
          nastavene jen na NJ karte). Pocita se po KARTE, ne po klientovi,
          aby se u klienta s vice kartami (ruzne arealy) nemichaly
          dohromady - viz konverzace s Danielem 2026-08-12.
        - Rozdil: Vynos - Naklad (zaporne = na te karte v tom obdobi
          prodelavame - typicky v zime kvuli teplu)."""
        from decimal import ROUND_CEILING
        from django.db.models import Sum
        from django.shortcuts import render
        from django.utils import timezone

        current_year = timezone.localdate().year
        periods = Period.objects.filter(year=current_year).order_by("year", "month")

        class_labels = InvoiceClassColor.label_map()

        def card_vynos(card, obdobi):
            """Skutecny najem karty za dane obdobi - zkraceny podle aktivnich
            dni, kdyz platnost karty zacina/konci uprostred mesice
            (ClientCard.rent_for_period). Zaokrouhluje nahoru, stejne jako
            "Přehled nájemného"."""
            return card.rent_for_period(obdobi)

        rows = []
        total_naklad = Decimal("0")
        total_vynos = Decimal("0")
        # Rozpad po KARTACH za cely rok - souhrnna tabulka pod prehledem
        # obdobi, aby slo videt, ktera karta je dlouhodobe ztratova (a cim),
        # ne jen ze v nejakem mesici vysel zaporny rozdil.
        # Viz konverzace s Danielem 2026-08-16.
        year_by_card = {}
        used_classes = set()
        for period in periods:
            pausal_lines = list(
                pronajimatele.omez(
                    BillingLine.objects.filter(period=period, is_billed=False),
                    "service_item__site", request,
                )
                .select_related("client_card__client", "service_item")
            )
            if not pausal_lines:
                continue
            card_ids_pausal = {line.client_card_id for line in pausal_lines}

            naklad = sum((line.amount for line in pausal_lines), Decimal("0"))

            cards = {
                card.id: card
                for card in ClientCard.objects.filter(id__in=card_ids_pausal)
                .select_related("client").prefetch_related("card_units")
            }

            # Rozpad obdobi po kartach, naklad clenene na Tridy zasobniku -
            # typicky duvod zaporneho rozdilu je teplo v zime.
            by_card = {}
            for line in pausal_lines:
                card = cards.get(line.client_card_id)
                if card is None:
                    continue
                detail = by_card.setdefault(line.client_card_id, {
                    "card": card, "by_class": {}, "naklad": Decimal("0"),
                })
                cls = line.service_item.invoice_class
                detail["by_class"][cls] = detail["by_class"].get(cls, Decimal("0")) + line.amount
                detail["naklad"] += line.amount
                used_classes.add(cls)

            vynos = Decimal("0")
            card_rows = []
            for detail in by_card.values():
                card_vynos_amount = card_vynos(detail["card"], period)
                vynos += card_vynos_amount
                card_rows.append({
                    "card": detail["card"],
                    "by_class": detail["by_class"],
                    "naklad": detail["naklad"],
                    "vynos": card_vynos_amount,
                    "rozdil": card_vynos_amount - detail["naklad"],
                })

                year_row = year_by_card.setdefault(detail["card"].id, {
                    "card": detail["card"], "by_class": {},
                    "naklad": Decimal("0"), "vynos": Decimal("0"), "mesicu": 0,
                })
                for cls, amount in detail["by_class"].items():
                    year_row["by_class"][cls] = year_row["by_class"].get(cls, Decimal("0")) + amount
                year_row["naklad"] += detail["naklad"]
                year_row["vynos"] += card_vynos_amount
                year_row["mesicu"] += 1

            card_rows.sort(key=lambda r: r["rozdil"])

            rows.append({
                "period": period,
                "pocet_klientu": len(card_ids_pausal),
                "naklad": naklad,
                "vynos": vynos,
                "rozdil": vynos - naklad,
                "card_rows": card_rows,
            })
            total_naklad += naklad
            total_vynos += vynos

        # Sloupce jen pro Tridy, ktere se v pausalnich radcich fakticky
        # objevily - jinak by tabulka mela pul tuctu prazdnych sloupcu.
        classes = [
            {"key": code, "label": class_labels[code]}
            for code, _ in InvoiceClassColor.choices()
            if code in used_classes
        ]
        year_rows = sorted(
            year_by_card.values(), key=lambda r: r["vynos"] - r["naklad"]
        )
        for year_row in year_rows:
            year_row["rozdil"] = year_row["vynos"] - year_row["naklad"]

        # Castky po Tridach jako SEZNAM v poradi sloupcu - sablona se do
        # dictu klicem ze smycky dostat neumi.
        for row in rows:
            for card_row in row["card_rows"]:
                card_row["class_amounts"] = [
                    card_row["by_class"].get(c["key"]) for c in classes
                ]
        for year_row in year_rows:
            year_row["class_amounts"] = [
                year_row["by_class"].get(c["key"]) for c in classes
            ]

        context = {
            **self.admin_site.each_context(request),
            "title": f"Paušální klienti - náklad vs výnos ({current_year})",
            "year": current_year,
            "rows": rows,
            "classes": classes,
            "year_rows": year_rows,
            "total_naklad": total_naklad,
            "total_vynos": total_vynos,
            "total_rozdil": total_vynos - total_naklad,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/billingline/report_pausalni.html", context)

    def report_grafy_trid_view(self, request):
        """Report (Reporty v menu): SVG sloupcovy graf (seskupene sloupce,
        ne CSS procentualni vysky - ty se v praxi ukazaly nespolehlive,
        viz konverzace s Danielem) vyvoje Nakladu (Kc) po Tridach za
        poslednich N obdobi. Geometrie se pocita tady v Pythonu (presne
        souradnice do <rect>), aby sablona byla jen tupe vykresleni bez
        vypoctu. Barvy podle dataviz skillu (categorical palette,
        pevne poradi slotu, viz core/static/... zadne externi zavislosti)."""
        import math
        from django.shortcuts import render
        from billing.item_summary import get_naklad_by_class

        try:
            n = int(request.GET.get("n", 6))
        except ValueError:
            n = 6

        sites = pronajimatele.arealy(request).order_by("name")
        site_id = request.GET.get("site")
        site = sites.filter(pk=site_id).first() if site_id else None

        # Poslednich N obdobi KONCE AKTUALNIM (Period.current), ne proste
        # nejnovejsich v DB - od tlacitka "Generovat pro celý rok" jsou
        # zalozene i budouci mesice, ktere jeste nemaji naklady, takze
        # graf ukazoval par prazdnych sloupcu a to jedine vyplnene
        # obdobi vypadalo jako ztracena data. Viz Daniel 2026-08-17.
        aktualni = Period.current()
        qs = Period.objects.order_by("-year", "-month")
        if aktualni is not None:
            qs = qs.filter(
                Q(year__lt=aktualni.year)
                | Q(year=aktualni.year, month__lte=aktualni.month)
            )
        periods = list(qs[:n])
        periods.reverse()  # chronologicky pro graf

        class_labels = InvoiceClassColor.label_map()
        class_order = [c for c, _ in InvoiceClassColor.choices()]
        # Barvy se berou z Nastavení -> Třídy (InvoiceClassColor), aby graf
        # drzel stejnou konvenci jako zbytek aplikace (Měřidla, Odečty,
        # Ceníky...). Do SVG se nevklada konkretni odstin, ale CSS trida +
        # fill/stroke="currentColor" - diky tomu se barva prepne se svetlym
        # / tmavym motivem a zmena v Nastavení se projevi bez zasahu do kodu
        # (viz core/views.py class_colors_css). Viz Daniel 2026-08-17.
        class_css = {
            code: InvoiceClassColor.css_class_for(code) for code, _ in InvoiceClassColor.choices()
        }

        # get_naklad_by_class dela jen par dotazu CELKEM (bez ohledu na pocet
        # obdobi) - viz jeji docstring (drive spadlo na WORKER TIMEOUT).
        naklad_by_period = get_naklad_by_class(
            periods, site=site, sites=pronajimatele.id_arealu(request)
        )
        raw_totals = [(period, naklad_by_period[period.id]) for period in periods]

        max_value = Decimal("0")
        for _, totals in raw_totals:
            for code in class_order:
                max_value = max(max_value, totals.get(code, Decimal("0")))

        def _nice_ceiling(value):
            """Zaokrouhli nahoru na "hezke" cislo (1/2/5 x 10^n) pro osu Y."""
            value = float(value)
            if value <= 0:
                return Decimal("100")
            exp = math.floor(math.log10(value))
            base = value / (10 ** exp)
            nice = 1 if base <= 1 else 2 if base <= 2 else 5 if base <= 5 else 10
            return Decimal(str(nice)) * (Decimal("10") ** exp)

        y_max = _nice_ceiling(max_value)

        # --- SVG geometrie spojnicoveho grafu (vse v px, pocitano tady) ---
        plot_h = 240
        left_margin = 72
        top_margin = 20
        bottom_margin = 34
        right_margin = 16
        col_w = 90
        plot_w = max(col_w * max(len(periods) - 1, 1), col_w)
        chart_w = left_margin + plot_w + right_margin
        chart_h = top_margin + plot_h + bottom_margin
        baseline_y = top_margin + plot_h

        def _y(value):
            if y_max == 0:
                return baseline_y
            return float(baseline_y - (value / y_max) * plot_h)

        def _x(i):
            if len(periods) <= 1:
                return left_margin + plot_w / 2
            return left_margin + (plot_w * i / (len(periods) - 1))

        gridlines = []
        for i in range(5):
            frac = Decimal(i) / Decimal(4)
            value = y_max * frac
            gy = _y(value)
            gridlines.append({
                "y": gy,
                "label_x": left_margin - 8,
                "label_y": gy + 4,
                "label": f"{value:,.0f}".replace(",", " "),
            })

        series = []
        for code in class_order:
            dots = []
            for i, (period, totals) in enumerate(raw_totals):
                value = totals.get(code, Decimal("0"))
                dots.append({"cx": _x(i), "cy": _y(value), "value": value, "label": class_labels[code]})
            points = " ".join(f"{d['cx']:.1f},{d['cy']:.1f}" for d in dots)
            series.append({
                "label": class_labels[code], "css_class": class_css[code],
                "points": points, "dots": dots,
            })

        period_labels = [
            {"x": _x(i), "label": str(period)} for i, (period, _) in enumerate(raw_totals)
        ]
        table_rows = [
            {"period": str(period), "values": [totals.get(code, Decimal("0")) for code in class_order]}
            for period, totals in raw_totals
        ]
        has_data = any(any(t.get(c, 0) for c in class_order) for _, t in raw_totals)

        context = {
            **self.admin_site.each_context(request),
            "title": "Grafy nákladů podle tříd",
            "class_choices": [
                {"code": code, "label": class_labels[code], "css_class": class_css[code]}
                for code in class_order
            ],
            "series": series,
            "period_labels": period_labels,
            "table_rows": table_rows,
            "gridlines": gridlines,
            "chart_w": chart_w,
            "chart_h": chart_h,
            "baseline_y": baseline_y,
            "left_margin": left_margin,
            "n": n,
            "sites": sites,
            "selected_site": site,
            "has_data": has_data,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/billingline/report_grafy_trid.html", context)

    def podil_vah_view(self, request):
        """Pro vybranou Polozku zasobniku a Obdobi ukaze vahu/meridlo a
        skutecny podil kazdeho jejiho klice - viz billing/weight_shares.py.
        Vyber Polozky je pres <select> seskupeny podle Arealu a Tridy, aby
        se v ~50+ polozkach dalo rychle najit.

        Jde vybrat i primo Meridlem (napr. "chci videt podily na E_SPOL")
        misto Polozky - to se dopredu nevi, protoze jedno Meridlo muze byt
        napojene na klice ve VICE Polozkach (viz find_items_for_meter). Pri
        jedne shode se rovnou preskoci na jeji Podil vah (s zvyraznenim
        radku patricich tomuto Meridlu - jinak by v tabulce vsech klicu
        polozky zapadlo mezi ostatni). Pri vic shodach se nabidne vyber,
        pri nule hlaska, ze se nikde nepouziva."""
        from django.db.models import Q
        from django.shortcuts import render
        from billing.weight_shares import find_items_for_meter, get_weight_share_data

        item_id = request.GET.get("item")
        meter_id = request.GET.get("meter")
        period_id = request.GET.get("period")

        periods = Period.objects.all()
        period = periods.filter(pk=period_id).first() if period_id else Period.current()

        items = pronajimatele.omez(
            ServicePoolItem.objects, "site", request
        ).select_related("site").order_by("site__name", "invoice_class", "name")
        item = items.filter(pk=item_id).first() if item_id else None

        selected_meter = (
            pronajimatele.omez(Meter.objects, "site", request)
            .select_related("site").filter(pk=meter_id).first()
            if meter_id else None
        )
        meter_choice_items = None
        if selected_meter and item is None:
            matches = find_items_for_meter(selected_meter)
            if len(matches) == 1:
                item = matches[0]
            elif len(matches) > 1:
                meter_choice_items = matches

        class_labels = InvoiceClassColor.label_map()
        item_groups = {}
        for it in items:
            key = (it.site.name, class_labels[it.invoice_class])
            item_groups.setdefault(key, []).append(it)

        # Jen meridla, ktera se v nejake Polozce/Klici skutecne pouzivaji
        # pro vypocet podilu - do vyberu nema smysl pridavat merici
        # meridla bez vazby na zadny Klic.
        relevant_meters = (
            pronajimatele.omez(Meter.objects, "site", request)
            .filter(Q(service_items__isnull=False) | Q(submeter_keys__isnull=False))
            .select_related("site").distinct().order_by("site__name", "code")
        )
        meter_groups = {}
        for m in relevant_meters:
            meter_groups.setdefault(m.site.name, []).append(m)

        data = get_weight_share_data(item, period) if (item and period) else None

        context = {
            **self.admin_site.each_context(request),
            "title": "Podíl vah",
            "periods": periods,
            "selected_period": period,
            "item_groups": [
                {"label": f"{site} – {cls}", "items": its} for (site, cls), its in item_groups.items()
            ],
            "selected_item": item,
            "meter_groups": [{"label": site, "meters": ms} for site, ms in meter_groups.items()],
            "selected_meter": selected_meter,
            "meter_choice_items": meter_choice_items,
            "highlight_meter_id": selected_meter.pk if selected_meter else None,
            "data": data,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/billingline/podil_vah.html", context)

    def prehled_view(self, request):
        """Interni souhrn Naklad/Vynos PO POLOZKACH zasobniku za obdobi
        (ne po klientech) - kolik polozka skutecne stoji vs. kolik se z
        ni vyfakturuje klientum, vc. zisku/ztraty. Viz billing/
        item_summary.py a konverzace s Danielem (chtel oddeleny prehled
        od per-klientskeho Detailu, se sumaci za vsechny tridy). Druha
        varianta (prehled_meridla_view) navic rozepisuje merene polozky
        po jednotlivych meridlech - obe existuji soubezne, ať si Daniel
        vybere, kterou chce pouzivat dal."""
        return self._prehled(request, with_meters=False, template="admin/core/billingline/prehled.html")

    def prehled_meridla_view(self, request):
        """Stejne jako prehled_view, ale s rozpadem merenych polozek na
        jednotliva meridla (viz billing/item_summary.py
        get_item_summary_rows(with_meters=True))."""
        return self._prehled(
            request, with_meters=True, template="admin/core/billingline/prehled_meridla.html"
        )

    def _prehled(self, request, with_meters, template):
        from django.shortcuts import render
        from billing.item_summary import get_item_summary_rows

        period_id = request.GET.get("period")
        site_id = request.GET.get("site")

        periods = Period.objects.all()
        period = periods.filter(pk=period_id).first() if period_id else None
        if period is None:
            period = Period.current()

        sites = pronajimatele.arealy(request).order_by("name")

        class_labels = InvoiceClassColor.label_map()
        groups_by_class = {key: [] for key, _ in InvoiceClassColor.choices()}
        totals = {
            "naklad": Decimal("0"), "vynos_fakturovano": Decimal("0"), "vynos_vcetne_pausalu": Decimal("0"),
        }

        if period is not None:
            site = pronajimatele.arealy(request).filter(pk=site_id).first() if site_id else None
            for row in get_item_summary_rows(
                period, site=site, with_meters=with_meters,
                sites=pronajimatele.id_arealu(request),
            ):
                groups_by_class.setdefault(row["invoice_class_key"], []).append(row)
                if row["naklad"] is not None:
                    totals["naklad"] += row["naklad"]
                totals["vynos_fakturovano"] += row["vynos_fakturovano"]
                totals["vynos_vcetne_pausalu"] += row["vynos_vcetne_pausalu"]

        def _subtotal(rows, key):
            values = [r[key] for r in rows if r[key] is not None]
            return sum(values, Decimal("0")) if values else None

        groups = [
            {
                "label": class_labels[key],
                "rows": rows,
                "naklad": _subtotal(rows, "naklad"),
                "vynos_fakturovano": _subtotal(rows, "vynos_fakturovano"),
                "rozdil_fakturovano": _subtotal(rows, "rozdil_fakturovano"),
                "vynos_vcetne_pausalu": _subtotal(rows, "vynos_vcetne_pausalu"),
                "rozdil_vcetne_pausalu": _subtotal(rows, "rozdil_vcetne_pausalu"),
            }
            for key, rows in groups_by_class.items() if rows
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": "Přehled nákladů a výnosů" + (" (rozpad na měřidla)" if with_meters else ""),
            "with_meters": with_meters,
            "periods": periods,
            "sites": sites,
            "selected_period": period,
            "selected_site_id": int(site_id) if site_id else None,
            "groups": groups,
            "total_naklad": totals["naklad"],
            "total_vynos_fakturovano": totals["vynos_fakturovano"],
            "total_rozdil_fakturovano": totals["vynos_fakturovano"] - totals["naklad"],
            "total_vynos_vcetne_pausalu": totals["vynos_vcetne_pausalu"],
            "total_rozdil_vcetne_pausalu": totals["vynos_vcetne_pausalu"] - totals["naklad"],
            "opts": self.model._meta,
        }
        return render(request, template, context)

    def detail_client_view(self, request, client_id):
        """Podrobny detail po jednotlivych Klicich pro jednoho klienta (viz
        billing/key_detail.py) - otevira se kliknutim na klienta v detail_view."""
        from django.shortcuts import redirect, render
        from billing.key_detail import get_key_rows_for_client

        # Klienti maji vlastni pravidlo (klient bez karty je videt vsude,
        # pronajimatel taky) - proto pronajimatele.klienti, ne get_queryset
        # tohohle adminu, ktery vraci Polozky. Bez toho sel po prepnuti
        # pronajimatele otevrit rozpad vyuctovani ciziho klienta.
        # Daniel 2026-08-25.
        client = pronajimatele.klienti(request).filter(pk=client_id).first()
        if client is None:
            self.message_user(request, "Klient patří jinému pronajímateli.",
                              level=messages.ERROR)
            return redirect("admin:core_billingline_detail")
        period_id = request.GET.get("period")
        period = Period.objects.filter(pk=period_id).first() if period_id else Period.current()

        groups = []
        warnings = []
        grand_total = Decimal("0")
        if period is not None:
            rows, warnings, item_losses = get_key_rows_for_client(client, period)
            class_labels = InvoiceClassColor.label_map()
            groups_by_class = {key: [] for key, _ in InvoiceClassColor.choices()}
            losses_by_class = {key: [] for key, _ in InvoiceClassColor.choices()}
            for row in rows:
                groups_by_class.setdefault(row["invoice_class_key"], []).append(row)
                grand_total += row["amount"]
            for loss in item_losses:
                losses_by_class.setdefault(loss["invoice_class_key"], []).append(loss)
            groups = [
                {
                    "label": class_labels[key], "rows": rs,
                    "subtotal": sum((r["amount"] for r in rs), Decimal("0")),
                    "losses": losses_by_class.get(key, []),
                }
                for key, rs in groups_by_class.items() if rs
            ]

        context = {
            **self.admin_site.each_context(request),
            "title": f"Detail podle klíčů - {client.name}",
            "client": client,
            "periods": Period.objects.all(),
            "selected_period": period,
            "groups": groups,
            "grand_total": grand_total,
            "warnings": warnings,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/billingline/detail_client.html", context)

    def detail_view(self, request):
        """Interni audit tabulka pro kontrolu vypoctu (ne pro klienty) - jeden
        radek za kazdy BillingLine (= karta klienta x polozka zasobniku v danem
        obdobi), s odectenymi stavy mericí, spotrebou, podilem, jednotkami,
        cenou za jednotku a celkovou castkou. Secteno po tridach a celkem."""
        period_id = request.GET.get("period")
        site_id = request.GET.get("site")

        periods = Period.objects.all()
        period = periods.filter(pk=period_id).first() if period_id else None
        if period is None:
            period = Period.current()

        sites = pronajimatele.arealy(request).order_by("name")

        groups_by_class = {key: [] for key, _ in InvoiceClassColor.choices()}
        grand_total = Decimal("0")

        if period is not None:
            qs = (
                pronajimatele.omez(
                    BillingLine.objects.filter(period=period),
                    "service_item__site", request,
                )
                .select_related(
                    "client_card__client", "client_card__unit",
                    "service_item", "service_item__meter", "service_item__site",
                )
                .order_by("service_item__name", "client_card__client__name")
            )
            if site_id:
                qs = qs.filter(service_item__site_id=site_id)

            meter_cache = {}
            prev_period = period.previous_period()

            for line in qs:
                si = line.service_item
                meter = si.meter
                previous_state = current_state = total_consumption = None
                if meter is not None:
                    if meter.id not in meter_cache:
                        current_reading = meter.readings.filter(period=period).first()
                        previous_reading = (
                            meter.readings.filter(period=prev_period).first() if prev_period else None
                        )
                        meter_cache[meter.id] = {
                            "previous": previous_reading.value if previous_reading else None,
                            "current": current_reading.value if current_reading else None,
                            "total_consumption": meter.consumption_for(period),
                        }
                    cached = meter_cache[meter.id]
                    previous_state = cached["previous"]
                    current_state = cached["current"]
                    total_consumption = cached["total_consumption"]

                calc = line.calc_detail or {}

                row = {
                    "client": line.client_card.client.name,
                    "client_id": line.client_card.client_id,
                    "card": line.client_card.description or f"Karta {line.client_card.client}",
                    "site": si.site.name,
                    "service_item": si.name,
                    "previous_state": previous_state,
                    "current_state": current_state,
                    "total_consumption": total_consumption,
                    "share": line.share,
                    "units": line.units,
                    "unit_of_measure": calc.get("unit_of_measure") or "",
                    "price_per_unit": calc.get("price_per_unit"),
                    "amount": line.amount,
                    "is_billed": line.is_billed,
                }
                groups_by_class.setdefault(si.invoice_class, []).append(row)
                grand_total += line.amount

        class_labels = InvoiceClassColor.label_map()
        groups = [
            {
                "label": class_labels[key],
                "rows": rows,
                "subtotal": sum((r["amount"] for r in rows), Decimal("0")),
            }
            for key, rows in groups_by_class.items() if rows
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": "Detail výpočtu vyúčtování",
            "periods": periods,
            "sites": sites,
            "selected_period": period,
            "selected_site_id": int(site_id) if site_id else None,
            "groups": groups,
            "grand_total": grand_total,
            "opts": self.model._meta,
        }
        from django.shortcuts import render
        return render(request, "admin/core/billingline/detail.html", context)

    @admin.display(description="Karta klienta", ordering="client_card")
    def client_card_display(self, obj):
        return obj.client_card.description or f"Karta {obj.client_card.client}"

    @admin.display(description="Částka (Kč)", ordering="amount")
    def amount_display(self, obj):
        return _format_kc(obj.amount)

    @admin.display(description="Podíl", ordering="share")
    def share_display(self, obj):
        if obj.share is None:
            return "—"
        return f"{obj.share * 100:.3f} %"

    def has_add_permission(self, request):
        return False

    @admin.action(description="Vygenerovat vyúčtování klienta (PDF)")
    def generovat_vyuctovani_pdf(self, request, queryset):
        from io import BytesIO
        from django.http import HttpResponse
        from billing.statement_generator import generate_client_statement_pdf

        client_ids = set(queryset.values_list("client_card__client_id", flat=True))
        period_ids = set(queryset.values_list("period_id", flat=True))
        if len(client_ids) != 1 or len(period_ids) != 1:
            self.message_user(
                request,
                "Vyber řádky jen jednoho klienta a jednoho období (nejdřív filtruj podle "
                "Období a vyhledej klienta, pak označ jeho řádky).",
                level=messages.ERROR,
            )
            return None

        client = Client.objects.get(pk=client_ids.pop())
        period = Period.objects.get(pk=period_ids.pop())

        buf = BytesIO()
        generate_client_statement_pdf(client, period, buf)
        filename = f"vyuctovani_{client.code or client.pk}_{period.year}_{period.month:02d}.pdf"
        response = HttpResponse(buf.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@admin.register(Floorplan)
class FloorplanAdmin(PodlePronajimatele, ModelAdmin):
    """Planky (2D pudorysy). Tvary ploch zustavaji ve vykresu, obsazenost
    v Kartach - parovani je jen pres `id` polygonu (viz core/floorplan.py)."""
    cesta_k_arealu = "site"


    list_display = ("name", "site", "order", "ploch", "velikost", "is_active", "prohlizec_odkaz")
    list_filter = ("site", "is_active")
    search_fields = ("name", "note")
    ordering = ("site", "order", "name")
    actions = ["zmensit_vykres"]

    @display(description="Velikost")
    def velikost(self, obj):
        return "%.2f MB" % (len(obj.svg_text or "") / 1024 / 1024)

    def _plan_pronajimatele(self, request, plan_id):
        """Planek zvoleneho pronajimatele, nebo None.

        Planek se otevira primo z URL (prohlizec/<id>/), takze po
        prepnuti pronajimatele v hlavicce menu zustala stranka viset na
        planku, ktery uz pod zvoleneho pronajimatele nepatri - videl tedy
        cizi budovu vcetne jmen najemcu v prehledu vedle vykresu. Areal
        pronajimatele urcuje Site.landlord, takze staci stejny filtr jako
        v PodlePronajimatele.get_queryset. Daniel 2026-08-25.
        """
        return self.get_queryset(request).filter(pk=plan_id).first()

    def _presmeruj_cizi_planek(self, request):
        from django.shortcuts import redirect

        self.message_user(
            request,
            "Plánek patří jinému pronajímateli – otevřel jsem seznam plánků.",
            level=messages.INFO,
        )
        return redirect("admin:core_floorplan_changelist")

    @admin.action(description="Zmenšit výkres (vyčistit balast a zkrátit souřadnice)")
    def zmensit_vykres(self, request, queryset):
        """Vyhodi zbytky po exportu z CADu a zkrati souradnice na jedno
        desetinne misto - viz core.floorplan.zmensi. Puvodne nahrany soubor
        zustava netknuty, meni se jen kopie v databazi, ze ktere se kresli."""
        from core.floorplan import zmensi

        celkem = 0
        for plan in queryset:
            try:
                text = plan.read_svg()
            except Exception as potiz:
                self.message_user(request, f"{plan.name}: výkres nejde přečíst – {potiz}",
                                  level=messages.ERROR)
                continue

            novy, prehled = zmensi(text)
            if prehled["usporeno"] <= 0 and not prehled["smazano"]:
                self.message_user(request, f"{plan.name}: už je zmenšený, nic k úpravě.")
                continue

            # pres queryset, aby se obesel Floorplan.save() a nesahal na soubor
            Floorplan.objects.filter(pk=plan.pk).update(svg_text=novy)
            plan.svg_text = novy
            celkem += prehled["usporeno"]
            self.message_user(request, (
                "{}: smazáno {} tvarů mimo výkres, {:.2f} → {:.2f} MB "
                "(úspora {:.0f} %)".format(
                    plan.name, prehled["smazano"],
                    prehled["pred"] / 1024 / 1024, prehled["po"] / 1024 / 1024,
                    100 - 100.0 * prehled["po"] / prehled["pred"],
                )
            ))

        if celkem:
            self.message_user(request, "Celkem ušetřeno %.2f MB. Menší je i PDF Karty nájemce."
                              % (celkem / 1024 / 1024))

    @display(description="Ploch ve výkresu")
    def ploch(self, obj):
        from core.floorplan import kody_ploch

        try:
            pronajimane, spolecne = kody_ploch(obj.read_svg())
        except Exception:
            return "chyba čtení"
        return f"{len(pronajimane)} pronajímaných, {len(spolecne)} společných"

    @display(description="")
    def prohlizec_odkaz(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj.pk:
            return ""
        url = reverse("admin:core_floorplan_prohlizec", args=[obj.pk])
        return format_html('<a class="rx-btn rx-btn-primary rx-btn-sm" href="{}">Prohlížeč</a>', url)

    def get_urls(self):
        from django.urls import path

        custom = [
            path(
                "prohlizec/<int:plan_id>/",
                self.admin_site.admin_view(self.prohlizec_view),
                name="core_floorplan_prohlizec",
            ),
            path(
                "kontrola/",
                self.admin_site.admin_view(self.kontrola_view),
                name="core_floorplan_kontrola",
            ),
            path(
                "prevod/<int:plan_id>/",
                self.admin_site.admin_view(self.prevod_view),
                name="core_floorplan_prevod",
            ),
        ]
        return custom + super().get_urls()

    def prevod_view(self, request, plan_id):
        """Převod vybraných ploch z plánku na Kartu jiného klienta.

        Dva kroky: nejdřív se ukáže, co přesně se stane (které Karty se
        uzavřou, co vznikne, jak se přepočítají klíče), a teprve po
        potvrzení se to zapíše. Zápis je v jedné transakci."""
        from datetime import date

        from django.shortcuts import redirect, render

        from core.floorplan_prevod import (
            REZIM_NAVAZAT, REZIM_NOVA, REZIM_PRIDAT, karta_klienta_k_datu, priprav, proved,
        )

        plan = self._plan_pronajimatele(request, plan_id)
        if plan is None:
            return self._presmeruj_cizi_planek(request)
        kody = [k for k in request.POST.getlist("plochy") or
                request.GET.get("plochy", "").split(",") if k]
        units = list(Unit.objects.filter(site=plan.site, name__in=kody))

        klient = Client.objects.filter(pk=request.POST.get("klient")).first()
        sazba = request.POST.get("sazba") or None
        datum = None
        if request.POST.get("datum"):
            try:
                datum = date.fromisoformat(request.POST["datum"])
            except ValueError:
                messages.error(request, "Datum nedává smysl.")

        prevod = None
        cil_karta = None
        rezim = request.POST.get("rezim") or ""
        if klient and datum:
            cil_karta = karta_klienta_k_datu(klient, datum)
            if not cil_karta:
                rezim = REZIM_NOVA
            elif rezim not in (REZIM_NOVA, REZIM_NAVAZAT, REZIM_PRIDAT):
                # když karta začíná přesně v den převodu, není co uzavírat
                rezim = REZIM_PRIDAT if cil_karta.valid_from == datum else REZIM_NAVAZAT

        if klient and datum and units:
            prevod = priprav(
                units, klient, datum, Decimal(sazba) if sazba else None,
                cil_karta if rezim != REZIM_NOVA else None, rezim,
            )

            if request.POST.get("potvrzeno") and not prevod.potize:
                nova = proved(prevod)
                self.message_user(
                    request,
                    "Plochy převedeny na %s od %s. Zkontroluj klíče, které se z výměry "
                    "odvodit nedají – teplo, voda, paušály." % (klient, datum),
                )
                return redirect(f"/admin/core/clientcard/{nova.pk}/change/")

        return render(request, "admin/core/floorplan/prevod.html", {
            **self.admin_site.each_context(request),
            "plan": plan,
            "kody": kody,
            "units": units,
            "klienti": pronajimatele.klienti(
                request, Client.objects.filter(is_active=True)).order_by("name"),
            "klient": klient,
            "datum": datum,
            "sazba": sazba,
            "prevod": prevod,
            "cil_karta": cil_karta,
            "rezim": rezim,
            "REZIM_NOVA": REZIM_NOVA,
            "REZIM_NAVAZAT": REZIM_NAVAZAT,
            "REZIM_PRIDAT": REZIM_PRIDAT,
            "opts": self.model._meta,
            "title": "Převod ploch na Kartu",
        })

    def prohlizec_view(self, request, plan_id):
        """Planek obarveny podle obsazenosti k zadanemu datu. SVG se vklada
        primo do stranky (ne pres <img>), jinak by se do ploch nedalo klikat
        ani je barvit CSS."""
        from datetime import date

        from django.shortcuts import render
        from django.utils.safestring import mark_safe

        from core.floorplan import oznac_plochy, stavy_ploch

        plan = self._plan_pronajimatele(request, plan_id)
        if plan is None:
            return self._presmeruj_cizi_planek(request)

        # Období má přednost před datem: Daniel s ním pracuje běžněji než
        # s kalendářem a stav plánku se mění hlavně mezi měsíci.
        k_datu = date.today()
        vybrane_obdobi = None
        obdobi_id = request.GET.get("obdobi")
        if obdobi_id:
            vybrane_obdobi = Period.objects.filter(pk=obdobi_id).first()
        if vybrane_obdobi:
            k_datu = date(vybrane_obdobi.year, vybrane_obdobi.month, 1)
        else:
            zadane = request.GET.get("datum")
            if zadane:
                try:
                    k_datu = date.fromisoformat(zadane)
                except ValueError:
                    messages.warning(request, "Datum nedává smysl, používám dnešek.")

        stavy = stavy_ploch(plan.site, k_datu)
        try:
            svg = oznac_plochy(plan.read_svg(), stavy)
            chyba = None
        except Exception as potiz:
            svg, chyba = "", str(potiz)

        # prehled vedle plánku - jen plochy, ktere na TOMHLE planku jsou
        from core.floorplan import kody_ploch

        try:
            kody, _ = kody_ploch(plan.read_svg())
        except Exception:
            kody = []
        radky = []
        for kod in sorted(kody):
            udaje = stavy.get(kod) or {"stav": "neprirazeno", "popis": "Není na žádné platné Kartě"}
            radky.append({"kod": kod, **udaje})

        return render(request, "admin/core/floorplan/prohlizec.html", {
            **self.admin_site.each_context(request),
            "plan": plan,
            "svg": mark_safe(svg),
            "chyba": chyba,
            "k_datu": k_datu,
            "obdobi": Period.objects.all()[:36],
            "vybrane_obdobi": vybrane_obdobi,
            "radky": radky,
            "plany_arealu": Floorplan.objects.filter(site=plan.site, is_active=True),
            "opts": self.model._meta,
            "title": f"Plánek – {plan}",
        })

    def kontrola_view(self, request):
        """Kontrola parovani: co je ve vykresu a nema Prostor v DB, a naopak
        ktere Prostory arealu nejsou na zadnem planku."""
        from django.shortcuts import render

        from core.floorplan import kontrola_parovani

        sites = list(pronajimatele.arealy(request).filter(floorplans__is_active=True).distinct())
        vybrany_id = request.GET.get("site")
        vybrany = None
        if vybrany_id:
            vybrany = next((s for s in sites if str(s.pk) == vybrany_id), None)
        if vybrany is None and sites:
            vybrany = sites[0]

        vysledek = kontrola_parovani(vybrany) if vybrany else None
        return render(request, "admin/core/floorplan/kontrola.html", {
            **self.admin_site.each_context(request),
            "sites": sites,
            "vybrany": vybrany,
            "vysledek": vysledek,
            "opts": self.model._meta,
            "title": "Kontrola párování plánků",
        })
