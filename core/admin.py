from decimal import Decimal

from django.contrib import admin, messages
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
from .admin_mixins import ModelAdmin, TabularInline

from .models import (
    Client, ClientCard, Contract, Site, Unit, CardUnit,
    Meter, MeterReading, Period, InflationRate, SupplyPoint,
    ServicePoolItem, AllocationKey, PriceList, CostEntry, BillingLine, UnitService
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
    panelu vubec nezobrazi. Viz DefaultToLatestPeriodMixin."""
    title = "výchozí období"
    parameter_name = "_pd"

    def lookups(self, request, model_admin):
        return ()

    def queryset(self, request, queryset):
        return queryset


class DefaultToLatestPeriodMixin:
    """Pri prvnim otevreni seznamu (bez explicitne zvoleneho Obdobi)
    presmeruje na filtr podle nejnovejsiho Obdobi (Period.Meta.ordering =
    ["-year", "-month"]) - stejna konvence uz existuje na custom admin
    views core_billingline_detail_client/core_billingline_detail (viz
    Period.objects.first() tam). Marker '_pd' v querystringu odlisi
    "cerstve otevreni" od situace, kdy uzivatel filtr na Obdobi vedome
    zrusil (klikl na 'Vše' u filtru) - jinak by ho to porad vracelo zpet
    na nejnovejsi obdobi a nedalo by se videt vic obdobi najednou.

    DULEZITE: kazdy ModelAdmin pouzivajici tenhle mixin MUSI mit
    _PeriodDefaultMarkerFilter v list_filter, jinak viz FieldError
    popsany u _PeriodDefaultMarkerFilter vyse."""
    default_period_filter_param = "period__id__exact"

    def changelist_view(self, request, extra_context=None):
        if self.default_period_filter_param not in request.GET and "_pd" not in request.GET:
            latest = Period.objects.first()
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
class SiteAdmin(ModelAdmin):
    list_display = ("name", "address")
    search_fields = ("name",)
    inlines = [UnitInline]


class UnitServiceInlineBase(TabularInline):
    model = UnitService
    extra = 0
    collapsible = True

    class Media:
        css = {"all": ("core/css/select_width_fix.css",)}

    # Mapovani tridy sluzby na typ mericí (pro tridu "other" mericí nejsou)
    METER_TYPE_FOR_CLASS = {
        "electricity": "electricity",
        "water": "water",
        "heat": "heat",
    }

    def get_formset(self, request, obj=None, **kwargs):
        self.parent_obj = obj
        return super().get_formset(request, obj, **kwargs)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            service_item__invoice_class=self.invoice_class
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        parent = getattr(self, "parent_obj", None)
        if db_field.name == "service_item":
            qs = ServicePoolItem.objects.filter(invoice_class=self.invoice_class)
            if parent is not None:
                qs = qs.filter(site=parent.site)
            kwargs["queryset"] = qs
        elif db_field.name == "meter":
            meter_type = self.METER_TYPE_FOR_CLASS.get(self.invoice_class)
            if meter_type:
                qs = Meter.objects.filter(meter_type=meter_type)
                if parent is not None:
                    qs = qs.filter(site=parent.site)
            else:
                qs = Meter.objects.none()
            kwargs["queryset"] = qs

        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "meter" and hasattr(formfield.widget, "can_delete_related"):
            formfield.widget.can_delete_related = False
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
        return formfield


class UnitServiceElectricityInline(UnitServiceInlineBase):
    invoice_class = "electricity"
    verbose_name = "Služba – Elektřina"
    verbose_name_plural = "Elektřina"


class UnitServiceWaterInline(UnitServiceInlineBase):
    invoice_class = "water"
    verbose_name = "Služba – Voda"
    verbose_name_plural = "Voda"


class UnitServiceHeatInline(UnitServiceInlineBase):
    invoice_class = "heat"
    verbose_name = "Služba – Teplo"
    verbose_name_plural = "Teplo"


class UnitServiceOtherInline(UnitServiceInlineBase):
    invoice_class = "other"
    verbose_name = "Služba – Ostatní"
    verbose_name_plural = "Ostatní"


@admin.register(Unit)
class UnitAdmin(DuplicateModelAdminMixin, ModelAdmin):
    list_display = ("name", "site", "purpose", "area_m2", "unit_type")
    list_select_related = ("site",)
    list_filter = ("site",)
    search_fields = ("name",)
    actions = ["duplicate_selected"]
    inlines = [
        UnitServiceElectricityInline,
        UnitServiceWaterInline,
        UnitServiceHeatInline,
        UnitServiceOtherInline,
    ]

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
            area = (
                Unit.objects.filter(pk=unit_id)
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
    fields = ("service_item", "allocation_type", "value", "meter", "unit", "deduct_from_pool", "is_billed")
    autocomplete_fields = ("service_item", "meter", "unit")

    class Media:
        css = {"all": ("core/css/select_width_fix.css",)}
        js = ("core/js/allocationkey_default_type.js",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            service_item__invoice_class=self.invoice_class
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "service_item":
            kwargs["queryset"] = ServicePoolItem.objects.filter(
                invoice_class=self.invoice_class
            )
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("meter", "unit") and hasattr(formfield.widget, "can_delete_related"):
            formfield.widget.can_delete_related = False
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
        return formfield


class AllocationKeyElectricityInline(AllocationKeyInlineBase):
    invoice_class = "electricity"
    verbose_name = "Klíč – Elektřina"
    verbose_name_plural = "Elektřina"


class AllocationKeyWaterInline(AllocationKeyInlineBase):
    invoice_class = "water"
    verbose_name = "Klíč – Voda"
    verbose_name_plural = "Voda"


class AllocationKeyHeatInline(AllocationKeyInlineBase):
    invoice_class = "heat"
    verbose_name = "Klíč – Teplo"
    verbose_name_plural = "Teplo"


class AllocationKeyOtherInline(AllocationKeyInlineBase):
    invoice_class = "other"
    verbose_name = "Klíč – Ostatní"
    verbose_name_plural = "Ostatní"


class CardUnitInline(TabularInline):
    model = CardUnit
    extra = 0
    fields = ("unit", "vymera_zasobnik", "area_m2_override", "rate_per_m2", "rocni_najem", "mesicni_najem")
    readonly_fields = ("vymera_zasobnik", "rocni_najem", "mesicni_najem")
    autocomplete_fields = ("unit",)
    verbose_name = "Plocha"
    verbose_name_plural = "Plochy a nájemné"

    class Media:
        js = ("core/js/cardunit_autofill.js",)

    def vymera_zasobnik(self, obj):
        if obj.unit and obj.unit.area_m2:
            return f"{obj.unit.area_m2} m²"
        return "—"
    vymera_zasobnik.short_description = "Výměra (zásobník)"

    def rocni_najem(self, obj):
        if obj.pk and obj.rate_per_m2 and obj.area_m2:
            return f"{obj.area_m2 * obj.rate_per_m2:.2f} Kč"
        return "—"
    rocni_najem.short_description = "Nájemné/rok"

    def mesicni_najem(self, obj):
        if obj.pk and obj.monthly_rent:
            return f"{obj.monthly_rent} Kč"
        return "—"
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
        return [(s.id, s.name) for s in Site.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                cards__card_units__unit__site_id=self.value()
            ).distinct()
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


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name_display", "code", "ico", "contact_email", "contact_phone", "is_active")
    search_fields = ("name", "ico", "code")
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
    conditional_fields = {
        "representative_name": "entity_type != 'fyzicka'",
        "representative_role": "entity_type != 'fyzicka'",
    }
    inlines = [ClientCardInline, ContractInline]
    actions = ["export_emaily"]

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
            return format_html('<span style="color:#dc2626; font-weight:600;">{}</span>', obj.name)
        if obj.is_landlord:
            return format_html('<span style="color:#ca8a04; font-weight:600;">{}</span>', obj.name)
        return obj.name

    class Media:
        js = ("core/js/ares_lookup.js",)

    def ares_button(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<button type="button" onclick="aresLookup()" '
            'style="padding:6px 16px; border-radius:6px; background:#2563eb; '
            'color:white; font-weight:600; border:none; cursor:pointer;">'
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
        ]
        return custom + urls

    def report_kontakty_view(self, request):
        """Report (Reporty v menu): jednoduchy seznam aktivnich klientu
        s kontaktnimi udaji, pro rychly prehled/export."""
        from django.shortcuts import render

        clients = Client.objects.filter(is_active=True).order_by("name")
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
    na_dobu_neurcitou = forms.BooleanField(
        label="Na dobu neurčitou", required=False,
        help_text="Zaškrtnuto (výchozí) = pole 'Platnost do' se nepoužije a zůstane prázdné.",
    )

    class Meta:
        model = Contract
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["number"].required = True
        self.fields["valid_from"].required = True
        self.fields["notice_period_months"].required = True
        if not self.instance.pk or not self.instance.valid_to:
            self.fields["na_dobu_neurcitou"].initial = True

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("na_dobu_neurcitou"):
            cleaned_data["valid_to"] = None
        return cleaned_data


@admin.register(Contract)
class ContractAdmin(DuplicateModelAdminMixin, ModelAdmin):
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

    fieldsets = (
        ("Základní údaje", {
            "fields": (("client", "site"), ("number", "signed_on"))
        }),
        ("Trvání a výpověď", {
            "fields": ("valid_from", "na_dobu_neurcitou", "valid_to", "notice_period_months")
        }),
        ("Kauce a pojištění", {
            "fields": (("deposit_czk", "deposit_paid"), "insurance_amount_czk")
        }),
        ("Inflační doložka", {
            "fields": ("has_inflation_clause", "inflation_increase_from")
        }),
        ("Fakturace a zástupce", {
            "fields": ("invoicing_email", ("representative_name", "representative_role"))
        }),
        ("Dokument", {
            "fields": ("generate_button", "document")
        }),
        ("Poznámka", {
            "fields": ("note",)
        }),
    )
    conditional_fields = {
        "valid_to": "na_dobu_neurcitou == false",
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
        from django.shortcuts import get_object_or_404, redirect
        from core.contract_generator import contract_to_template_data, fill_contract_template

        contract = get_object_or_404(Contract, pk=contract_id)
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
            '<a href="{}" '
            'style="padding:6px 16px; border-radius:6px; background:#2563eb; '
            'color:white; font-weight:600; text-decoration:none; display:inline-block;">'
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
            "fields": (("valid_from", "valid_to"), "notice_period_months")
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
class ClientCardAdmin(ModelAdmin):
    list_display = ("client", "description", "valid_from", "valid_to", "is_active")
    list_select_related = ("client",)
    list_filter = (ClientCardClientActiveFilter, ClientCardActiveFilter)
    autocomplete_fields = ("client",)
    search_fields = ("client__name", "description")
    fieldsets = (
        ("Základní údaje", {
            "fields": (("client", "description"), ("valid_from", "valid_to"), "is_active", "note")
        }),
        ("Čísla objednávek (na faktury)", {
            "fields": (("po_number_rent", "po_number_services"),)
        }),
        ("Karta nájemce (Příloha č. 1)", {
            "fields": ("signed_on", "generate_card_button", "document")
        }),
    )
    readonly_fields = ("generate_card_button",)

    def serialize_result(self, obj, to_field_name):
        # ClientCard.__str__ je schvalne prazdny (kvuli nadpisu v inline sekcich
        # na karte klienta) - autocomplete jinde (napr. u Klice) potrebuje
        # smysluplny popisek, proto se sestavuje tady zvlast.
        result = super().serialize_result(obj, to_field_name)
        result["text"] = obj.description or f"Karta {obj.client}"
        return result
    inlines = [
        CardUnitInline,
        AllocationKeyElectricityInline,
        AllocationKeyWaterInline,
        AllocationKeyHeatInline,
        AllocationKeyOtherInline,
    ]
    actions = ["kopie_karty"]

    @admin.action(description="Vytvořit kopii vybraných karet")
    def kopie_karty(self, request, queryset):
        for card in queryset:
            card.create_exact_copy()
        self.message_user(request, f"Vytvořeno {queryset.count()} kopií karet.")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
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

        units = Unit.objects.select_related("site").prefetch_related(
            "card_units__card__client"
        ).order_by("site__name", "name")

        conflicts_by_site = {}
        for unit in units:
            active_cards = {
                cu.card for cu in unit.card_units.all() if cu.card.is_active
            }
            clients = {card.client for card in active_cards}
            if len(clients) > 1:
                conflicts_by_site.setdefault(unit.site, []).append({
                    "unit": unit,
                    "cards": sorted(active_cards, key=lambda c: c.client.name),
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
        sites = Site.objects.order_by("name")

        cards = (
            ClientCard.objects.filter(is_active=True)
            .select_related("client")
            .prefetch_related("card_units__unit__site")
            .order_by("client__name")
        )
        if site_id:
            cards = cards.filter(card_units__unit__site_id=site_id).distinct()

        rows = []
        for card in cards:
            card_units = list(card.card_units.all())
            if not card_units:
                continue
            total_area = sum((cu.area_m2 or Decimal("0")) for cu in card_units)
            raw_monthly = sum((cu.monthly_rent or Decimal("0") for cu in card_units), Decimal("0"))
            total_monthly = raw_monthly.quantize(Decimal("1"), rounding=ROUND_CEILING)
            sites_of_card = {cu.unit.site for cu in card_units}
            rows.append({
                "client": card.client,
                "card": card,
                "sites": sites_of_card,
                "area_m2": total_area,
                "monthly_rent": total_monthly,
                "yearly_rent": total_monthly * 12,
            })

        rows.sort(key=lambda r: r["client"].name)
        total_monthly = sum((r["monthly_rent"] for r in rows), Decimal("0"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Přehled nájemného",
            "sites": sites,
            "selected_site_id": int(site_id) if site_id else None,
            "rows": rows,
            "total_monthly": total_monthly,
            "total_yearly": total_monthly * 12,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/clientcard/report_najemne.html", context)

    def generate_card_and_download(self, request, card_id):
        from io import BytesIO
        from django.core.files.base import ContentFile
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        from core.client_card_generator import generate_client_card_document

        card = get_object_or_404(ClientCard, pk=card_id)
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
        return format_html(
            '<a href="{}" '
            'style="padding:6px 16px; border-radius:6px; background:#2563eb; '
            'color:white; font-weight:600; text-decoration:none; display:inline-block;">'
            'Generovat Kartu nájemce (.pdf)</a>',
            url,
        )
    generate_card_button.short_description = ""

    def kopie_view(self, request, card_id):
        """Obycejna kopie - stejny klient, okamzite, bez potvrzeni."""
        from django.shortcuts import redirect
        original = ClientCard.objects.get(pk=card_id)
        new_card = original.create_exact_copy()
        self.message_user(request, "Kopie karty byla vytvořena.")
        return redirect(f"/admin/core/clientcard/{new_card.pk}/change/")

    def kopie_klient_view(self, request, card_id):
        """Kopie na jineho klienta - napr. kdyz si prostor pronajme novy najemce."""
        from django.shortcuts import redirect, render
        original = ClientCard.objects.get(pk=card_id)

        if request.method == "POST":
            new_client = Client.objects.filter(pk=request.POST.get("new_client")).first()
            if not new_client:
                self.message_user(request, "Musíš vybrat klienta, na kterého se má karta zkopírovat.", level=messages.ERROR)
                return redirect(request.path)
            new_card = original.create_exact_copy(client=new_client)
            self.message_user(request, f"Kopie karty byla vytvořena pro klienta {new_client}.")
            return redirect(f"/admin/core/clientcard/{new_card.pk}/change/")

        context = {
            **self.admin_site.each_context(request),
            "title": "Kopírovat kartu na nového klienta",
            "original": original,
            "clients": Client.objects.filter(is_active=True).order_by("name"),
            "opts": self.model._meta,
        }
        return render(request, "admin/core/clientcard/kopie_form.html", context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["kopie_url"] = f"/admin/core/clientcard/kopie/{object_id}/"
        extra_context["kopie_klient_url"] = f"/admin/core/clientcard/kopie-klient/{object_id}/"
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
class MeterAdmin(DuplicateModelAdminMixin, ModelAdmin):
    list_display = (
        "code", "name", "site", "meter_type", "parent_meter", "supply_point",
        "reading_mode", "is_virtual", "unit_of_measure", "weight_unit_label",
    )
    list_select_related = ("site", "parent_meter", "supply_point")
    list_filter = ("site", "meter_type", "supply_point", "reading_mode", "is_virtual")
    search_fields = ("name", "code", "serial_number")
    autocomplete_fields = ("parent_meter", "supply_point")
    actions = ["duplicate_selected", "assign_supply_point"]
    inlines = [MeterReadingInline]

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
                "supply_points": SupplyPoint.objects.select_related("site").all(),
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
                ("meter_type", "unit_of_measure", "serial_number"),
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

            qs = Meter.objects.all()
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
        period = periods.filter(pk=period_id).first() if period_id else periods.first()

        sites = Site.objects.order_by("name")
        site = sites.filter(pk=site_id).first() if site_id else None

        groups = []
        if period is not None:
            meters_qs = (
                Meter.objects.select_related("site", "parent_meter")
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
            supplies_qs = SupplyPoint.objects.select_related("main_meter", "site")
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

            for type_code, type_label in Meter.MeterType.choices:
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
                    zakonne = realne = vahou = skutecne = None
                    if dodano is not None:
                        pct = sp.legal_loss_pct or Decimal("0")
                        realne = dodano / (Decimal("1") + pct / Decimal("100"))
                        zakonne = dodano - realne
                        vahou = realne - podmery
                        skutecne = vahou - spolecne
                        total_dodano = (total_dodano or Decimal("0")) + dodano
                    # Zaporne "skutecne ztraty" = namereno je vyssi nez realne
                    # dodane, tj. skutecne ztraty jsou MENSI nez zakonna
                    # rezerva (napr. 4 %) - to je v poradku, ne chyba. Ukazeme
                    # to jako nevycerpanou rezervu misto straselneho zaporu.
                    rezerva = -skutecne if (skutecne is not None and skutecne < 0) else None

                    supply_blocks.append({
                        "supply": sp, "dodano": dodano, "zakonne": zakonne,
                        "realne": realne, "podmery": podmery, "spolecne": spolecne,
                        "vahou": vahou, "skutecne": skutecne, "rezerva": rezerva,
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

                groups.append({
                    "label": type_label,
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

    def _unassigned_meters_queryset(self):
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

        return (
            Meter.objects.select_related("site")
            .exclude(pk__in=used_as_item_meter)
            .exclude(pk__in=used_as_key_meter)
            .exclude(pk__in=used_as_parent)
            .exclude(pk__in=used_as_unit_service_meter)
            .order_by("site__name", "code")
        )

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

    def report_neprirazena_view(self, request):
        """Report (Reporty v menu) s moznosti hromadne smazat vybrana
        nepouzita meridla (viz report_neprirazena_smazat_view)."""
        from django.shortcuts import render

        unused = list(self._unassigned_meters_queryset())
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

        safe_ids = set(self._unassigned_meters_queryset().values_list("pk", flat=True))
        safe_ids -= set(self._formula_protected_meter_ids().keys())

        to_delete = requested_ids & safe_ids
        skipped = requested_ids - safe_ids

        if to_delete:
            deleted_names = list(Meter.objects.filter(pk__in=to_delete).values_list("name", flat=True))
            Meter.objects.filter(pk__in=to_delete).delete()
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
    list_display = ("__str__", "status_badge", "days_in_period", "period_actions")
    list_filter = ("status",)
    ordering = ("-year", "-month")
    actions = [
        "spocitat_rozuctovani", "zkontrolovat_co_zadat", "vygenerovat_chybejici_naklady",
        "uzavrit_obdobi", "znovu_otevrit_obdobi",
    ]

    @display(
        description="Stav", ordering="status",
        label={Period.Status.OPEN.label: "success", Period.Status.CLOSED.label: "danger"},
    )
    def status_badge(self, obj):
        return obj.get_status_display()

    def changelist_view(self, request, extra_context=None):
        """Ulozi request na self, aby si ho action_buttons (list_display
        sloupec) mohl vzit pro CSRF token - list_display metody request
        normalne nedostavaji, tohle je bezny obchazeci trik."""
        self.request = request
        return super().changelist_view(request, extra_context)

    def _period_action_button(self, url, csrf_token, label, color, confirm_text):
        from django.utils.html import format_html
        return format_html(
            '<form method="post" action="{}" style="display:inline;" '
            'onsubmit="return confirm(\'{}\');">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" style="padding:4px 10px; border-radius:6px; border:none; '
            'color:white; font-weight:600; font-size:12px; cursor:pointer; white-space:nowrap; '
            'background:{};">{}</button>'
            '</form>',
            url, confirm_text, csrf_token, color, label,
        )

    def _period_link_button(self, url, label, color):
        from django.utils.html import format_html
        return format_html(
            '<a href="{}" target="_blank" style="padding:4px 10px; border-radius:6px; '
            'color:white; font-weight:600; font-size:12px; text-decoration:none; '
            'display:inline-block; white-space:nowrap; background:{};">{}</a>',
            url, color, label,
        )

    def period_actions(self, obj):
        from django.urls import reverse
        from django.middleware.csrf import get_token
        from django.utils.safestring import mark_safe

        token = get_token(self.request)
        odecty_url = f"{reverse('odecty')}?period={obj.pk}"
        buttons = [
            self._period_link_button(odecty_url, "Zadat odečty", "#2563eb"),
            self._period_action_button(
                reverse("admin:core_period_vypocet", args=[obj.pk]), token,
                "Výpočet", "#ca8a04", f"Spočítat rozúčtování za {obj} (všechny areály)?",
            ),
        ]
        # Otevrit ma smysl jen u uzavreneho obdobi a naopak - u
        # aktualniho stavu by tlacitko nic nezmenilo (viz konverzace
        # s Danielem).
        if obj.status == Period.Status.CLOSED:
            buttons.append(self._period_action_button(
                reverse("admin:core_period_otevrit", args=[obj.pk]), token,
                "Otevřít", "#16a34a", f"Znovu otevřít {obj}?",
            ))
        else:
            buttons.append(self._period_action_button(
                reverse("admin:core_period_zavrit", args=[obj.pk]), token,
                "Zavřít", "#dc2626", f"Uzavřít {obj}? Rozúčtování už pak nepůjde přepočítat.",
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
        ]
        return custom + urls

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
        from django.shortcuts import get_object_or_404
        if request.method != "POST":
            return self._redirect_back(request)
        period = get_object_or_404(Period, pk=period_id)
        self._spocitat_rozuctovani(request, Period.objects.filter(pk=period.pk), site=None)
        return self._redirect_back(request)

    def get_actions(self, request):
        actions = super().get_actions(request)
        for site in Site.objects.all():
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

            for item in ServicePoolItem.objects.select_related("site").all():
                cost_entry = CostEntry.objects.filter(service_item=item, period=period).first()
                if cost_entry is None:
                    if item.default_amount_czk is None:
                        missing_cost.append(item)
                    continue

                if cost_entry.amount_czk is not None or cost_entry.amount_units is None:
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
            if stale_price:
                text = "; ".join(
                    f"{item} (cena naposledy nastavena {price_period}, {age} měs. zpět)"
                    for item, price_period, age in stale_price
                )
                self.message_user(
                    request, f"{label}: platné ceny z dřívějška - zkontroluj, jestli se nezměnily: {text}",
                    level=messages.INFO,
                )
            if not (missing_cost or missing_price or stale_price):
                self.message_user(
                    request, f"{label}: vše zadané, nic nechybí.", level=messages.SUCCESS
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
            for item in ServicePoolItem.objects.all():
                if item.default_amount_czk is not None:
                    continue
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
class SupplyPointAdmin(ModelAdmin):
    list_display = ("name", "code", "site", "meter_type", "main_meter", "legal_loss_pct", "member_count")
    list_select_related = ("site", "main_meter")
    list_filter = ("site", "meter_type")
    search_fields = ("name", "code")
    autocomplete_fields = ("main_meter",)
    fieldsets = (
        (None, {
            "fields": (
                ("site", "meter_type"),
                ("name", "code"),
                "main_meter",
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

    @display(description="Počet měřidel")
    def member_count(self, obj):
        return obj.member_meters.count()


@admin.register(MeterReading)
class MeterReadingAdmin(DefaultToLatestPeriodMixin, ModelAdmin):
    list_display = ("meter", "period", "reading_date", "value", "reset_from_value")
    list_select_related = ("meter", "period")
    list_filter = ("meter__site", "meter__meter_type", "period", _PeriodDefaultMarkerFilter)
    search_fields = ("meter__code", "meter__name")
    autocomplete_fields = ("meter",)
    ordering = ("meter__code", "-period")


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
class ServicePoolItemAdmin(ModelAdmin):
    list_display = (
        "name", "site", "invoice_class", "unit", "meter", "jednotka",
        "default_allocation_type", "default_amount_czk_display", "weight_unit_label",
    )
    list_select_related = ("site", "unit", "meter")
    list_filter = ("site", "invoice_class")
    search_fields = ("name",)
    autocomplete_fields = ("unit", "meter")
    readonly_fields = ("meridla_prehled",)

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
            data = (
                ServicePoolItem.objects.filter(pk=item_id)
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

        qs = ServicePoolItem.objects.all()
        if site_id:
            qs = qs.filter(site_id=site_id)
        if invoice_class:
            qs = qs.filter(invoice_class=invoice_class)
        if term:
            qs = qs.filter(Q(name__icontains=term))

        qs = qs.order_by("name")[:50]
        return JsonResponse({"results": [{"id": i.id, "text": str(i)} for i in qs]})


@admin.register(AllocationKey)
class AllocationKeyAdmin(ModelAdmin):
    list_display = (
        "client_card_display", "service_item", "allocation_type", "value_display",
        "meter", "unit", "deduct_from_pool", "is_billed", "valid_from", "valid_to",
    )
    list_select_related = ("client_card", "client_card__client", "service_item", "service_item__site", "meter", "unit")
    list_filter = ("allocation_type", "deduct_from_pool", "is_billed")
    search_fields = ("meter__code", "meter__name", "client_card__client__name", "service_item__name")
    autocomplete_fields = ("client_card", "service_item", "meter", "unit")

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
class PriceListAdmin(DefaultToLatestPeriodMixin, ModelAdmin):
    list_display = ("service_item", "period", "price_per_unit_display", "note")
    list_select_related = ("service_item", "service_item__site", "period")
    list_filter = ("period", "service_item__site", _PeriodDefaultMarkerFilter)
    autocomplete_fields = ("service_item",)
    search_fields = ("service_item__name",)

    @admin.display(description="Cena za jednotku (Kč)", ordering="price_per_unit")
    def price_per_unit_display(self, obj):
        return _format_kc(obj.price_per_unit, decimals=4)


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
class CostEntryAdmin(DefaultToLatestPeriodMixin, ModelAdmin):
    """list_editable u amount_units/amount_czk - primo v seznamu (po
    filtru na Obdobi) jde zadat cisla u vice polozek najednou a ulozit
    jednim tlacitkem, misto otevirani kazdeho zaznamu zvlast. Kvuli tomu
    (Django to vyzaduje) je list_display_links presunuty na service_item,
    aby zustal jasny "odkazovaci" sloupec pro otevreni celeho formulare
    (napr. kvuli kontrolnim polim). Poznamka se v seznamu nezobrazuje
    (jen ve formulari zaznamu) - viz konverzace s Danielem."""
    list_display = (
        "trida", "service_item", "period", "amount_units", "amount_czk", "jednotka", "kc_za_jednotku",
        "amount_czk_display",
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

        items = ServicePoolItem.objects.exclude(default_amount_czk__isnull=True).select_related("site")
        site_id = request.GET.get("service_item__site__id__exact")
        if site_id:
            items = items.filter(site_id=site_id)
        invoice_class = request.GET.get("service_item__invoice_class__exact")
        if invoice_class:
            items = items.filter(invoice_class=invoice_class)
        items = items.exclude(cost_entries__period=period).order_by("invoice_class", "site__name", "name")

        class_labels = dict(ServicePoolItem.InvoiceClass.choices)
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
            attrs = {"class": " ".join([*INPUT_CLASSES, "text-right"]), "inputmode": "decimal"}
            if db_field.name == "amount_czk":
                attrs["suffix"] = "Kč"
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

        class_order = {code: i for i, (code, _) in enumerate(ServicePoolItem.InvoiceClass.choices)}
        whens = [When(service_item__invoice_class=code, then=i) for code, i in class_order.items()]
        qs = super().get_queryset(request)
        return qs.annotate(_trida_poradi=Case(*whens, output_field=IntegerField())).order_by(
            "_trida_poradi", "service_item__site", "service_item__name", "-period__year", "-period__month"
        )

    @admin.display(description="Třída")
    def trida(self, obj):
        return obj.service_item.get_invoice_class_display()

    @admin.display(description="Jednotka")
    def jednotka(self, obj):
        return _jednotka_polozky(obj.service_item)

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
class BillingLineAdmin(DefaultToLatestPeriodMixin, ModelAdmin):
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

        rows = []
        total_naklad = Decimal("0")
        total_vynos = Decimal("0")
        for period in periods:
            card_ids_pausal = set(
                BillingLine.objects.filter(period=period, is_billed=False)
                .values_list("client_card_id", flat=True)
            )
            if not card_ids_pausal:
                continue
            naklad = BillingLine.objects.filter(
                period=period, is_billed=False, client_card_id__in=card_ids_pausal,
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")

            vynos = Decimal("0")
            cards = ClientCard.objects.filter(id__in=card_ids_pausal).prefetch_related("card_units")
            for card in cards:
                raw_monthly = sum(
                    (cu.monthly_rent or Decimal("0") for cu in card.card_units.all()), Decimal("0")
                )
                vynos += raw_monthly.quantize(Decimal("1"), rounding=ROUND_CEILING)

            rows.append({
                "period": period,
                "pocet_klientu": len(card_ids_pausal),
                "naklad": naklad,
                "vynos": vynos,
                "rozdil": vynos - naklad,
            })
            total_naklad += naklad
            total_vynos += vynos

        context = {
            **self.admin_site.each_context(request),
            "title": f"Paušální klienti - náklad vs výnos ({current_year})",
            "year": current_year,
            "rows": rows,
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

        periods = list(Period.objects.order_by("-year", "-month")[:n])
        periods.reverse()  # chronologicky pro graf

        class_labels = dict(ServicePoolItem.InvoiceClass.choices)
        class_order = [code for code, _ in ServicePoolItem.InvoiceClass.choices]
        # Pevne poradi barevnych slotu (nikdy necyklovat) - viz dataviz
        # skill references/palette.md, kategoriala paleta sloty 1-5.
        class_colors = {
            "rent": "#2a78d6",
            "electricity": "#eb6834",
            "water": "#1baf7a",
            "heat": "#eda100",
            "other": "#e87ba4",
        }

        # get_naklad_by_class dela jen par dotazu CELKEM (bez ohledu na
        # pocet obdobi) - puvodne se tu volala get_item_summary_rows
        # jednou na kazde obdobi, coz pri 6 obdobich dohromady snadno
        # prekrocilo gunicorn WORKER TIMEOUT (30s), viz konverzace
        # s Danielem.
        naklad_by_period = get_naklad_by_class(periods)
        raw_totals = [(period, naklad_by_period[period.id]) for period in periods]

        max_value = Decimal("0")
        for _, totals in raw_totals:
            period_max = max(totals.values()) if totals else Decimal("0")
            max_value = max(max_value, period_max)

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

        # --- SVG geometrie (vse v px, pocitano tady, sablona uz jen kresli) ---
        plot_h = 240
        bar_w = 14
        bar_gap = 2
        cluster_gap = 22
        left_margin = 64
        top_margin = 30
        bottom_margin = 34
        cluster_w = len(class_order) * bar_w + (len(class_order) - 1) * bar_gap
        chart_w = left_margin + len(periods) * (cluster_w + cluster_gap) + cluster_gap
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
                "y": gy,
                "label_x": left_margin - 8,
                "label_y": gy + 4,
                "label": f"{value:,.0f}".replace(",", " "),
            })

        clusters = []
        x = left_margin + cluster_gap
        for period, totals in raw_totals:
            bars = []
            bx = x
            total = Decimal("0")
            for code in class_order:
                value = totals[code]
                total += value
                bar_top = _y(value)
                bars.append({
                    "x": bx,
                    "y": bar_top,
                    "w": bar_w,
                    "h": max(baseline_y - bar_top, 0),
                    "color": class_colors[code],
                    "label": class_labels[code],
                    "value": value,
                })
                bx += bar_w + bar_gap
            clusters.append({
                "period": period,
                "bars": bars,
                "label_x": x + cluster_w / 2,
                "total": total,
                "total_label_y": top_margin - 6,
                "period_label_y": baseline_y + 18,
            })
            x += cluster_w + cluster_gap

        context = {
            **self.admin_site.each_context(request),
            "title": "Grafy nákladů podle tříd",
            "class_choices": [
                {"code": code, "label": class_labels[code], "color": class_colors[code]}
                for code in class_order
            ],
            "clusters": clusters,
            "gridlines": gridlines,
            "chart_w": chart_w,
            "chart_h": chart_h,
            "baseline_y": baseline_y,
            "left_margin": left_margin,
            "n": n,
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
        period = periods.filter(pk=period_id).first() if period_id else periods.first()

        items = ServicePoolItem.objects.select_related("site").order_by("site__name", "invoice_class", "name")
        item = items.filter(pk=item_id).first() if item_id else None

        selected_meter = Meter.objects.select_related("site").filter(pk=meter_id).first() if meter_id else None
        meter_choice_items = None
        if selected_meter and item is None:
            matches = find_items_for_meter(selected_meter)
            if len(matches) == 1:
                item = matches[0]
            elif len(matches) > 1:
                meter_choice_items = matches

        class_labels = dict(ServicePoolItem.InvoiceClass.choices)
        item_groups = {}
        for it in items:
            key = (it.site.name, class_labels[it.invoice_class])
            item_groups.setdefault(key, []).append(it)

        # Jen meridla, ktera se v nejake Polozce/Klici skutecne pouzivaji
        # pro vypocet podilu - do vyberu nema smysl pridavat merici
        # meridla bez vazby na zadny Klic.
        relevant_meters = (
            Meter.objects.filter(Q(service_items__isnull=False) | Q(submeter_keys__isnull=False))
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
            period = periods.first()

        sites = Site.objects.order_by("name")

        class_labels = dict(ServicePoolItem.InvoiceClass.choices)
        groups_by_class = {key: [] for key, _ in ServicePoolItem.InvoiceClass.choices}
        totals = {
            "naklad": Decimal("0"), "vynos_fakturovano": Decimal("0"), "vynos_vcetne_pausalu": Decimal("0"),
        }

        if period is not None:
            site = Site.objects.filter(pk=site_id).first() if site_id else None
            for row in get_item_summary_rows(period, site=site, with_meters=with_meters):
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
        from django.shortcuts import get_object_or_404, render
        from billing.key_detail import get_key_rows_for_client

        client = get_object_or_404(Client, pk=client_id)
        period_id = request.GET.get("period")
        period = Period.objects.filter(pk=period_id).first() if period_id else Period.objects.first()

        groups = []
        warnings = []
        grand_total = Decimal("0")
        if period is not None:
            rows, warnings, item_losses = get_key_rows_for_client(client, period)
            class_labels = dict(ServicePoolItem.InvoiceClass.choices)
            groups_by_class = {key: [] for key, _ in ServicePoolItem.InvoiceClass.choices}
            losses_by_class = {key: [] for key, _ in ServicePoolItem.InvoiceClass.choices}
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
            period = periods.first()

        sites = Site.objects.order_by("name")

        groups_by_class = {key: [] for key, _ in ServicePoolItem.InvoiceClass.choices}
        grand_total = Decimal("0")

        if period is not None:
            qs = (
                BillingLine.objects.filter(period=period)
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

        class_labels = dict(ServicePoolItem.InvoiceClass.choices)
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
