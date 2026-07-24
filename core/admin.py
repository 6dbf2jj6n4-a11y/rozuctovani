from decimal import Decimal

from django.contrib import admin, messages
from django.contrib.auth.models import Group

admin.site.unregister(Group)
from django.contrib.auth.models import User as AuthUser

try:
    admin.site.unregister(AuthUser)
except admin.sites.NotRegistered:
    pass
from django import forms
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Client, ClientCard, Contract, Site, Unit, CardUnit,
    Meter, MeterReading, Period, InflationRate,
    ServicePoolItem, AllocationKey, PriceList, CostEntry, BillingLine, UnitService
)


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
class UnitAdmin(ModelAdmin):
    list_display = ("code", "name", "site", "purpose", "area_m2", "unit_type")
    list_filter = ("site",)
    search_fields = ("name", "code")
    inlines = [
        UnitServiceElectricityInline,
        UnitServiceWaterInline,
        UnitServiceHeatInline,
        UnitServiceOtherInline,
    ]

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
    fields = ("service_item", "allocation_type", "value", "meter", "unit", "deduct_from_pool")
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
    model = ClientCard
    form = ClientCardInlineForm
    extra = 0
    fields = ("description_link", "valid_from", "valid_to", "is_active", "note")
    readonly_fields = ("description_link",)
    can_delete = True
    verbose_name = "Karta"
    verbose_name_plural = "Karty klientů"

    def description_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse("admin:core_clientcard_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.description or "—")
    description_link.short_description = "Popis karty"


class ContractInline(TabularInline):
    """Jedna inline sekce pro pridavani i editaci Smluv klienta primo zde.
    Cislo smlouvy je bezne editovatelne pole (zadava se hned pri pridani).
    Pokrocila pole (generovani dokumentu, poznamka) jsou jen na vlastni
    strance Smlouvy - tam vede odkaz "Zmenit" (show_change_link)."""
    model = Contract
    extra = 0
    fields = ("number", "site", "valid_from", "signed_on", "deposit_czk", "deposit_paid", "has_inflation_clause")
    autocomplete_fields = ("site",)
    show_change_link = True
    verbose_name = "Smlouva"
    verbose_name_plural = "Smlouvy"


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
    list_display = (
        "name_display", "code", "ico", "insolvency_display",
        "contact_email", "contact_phone", "is_active", "is_landlord",
    )
    search_fields = ("name", "ico", "code")
    list_filter = (ActiveClientFilter, "is_landlord", SiteFilter, "insolvency_status")
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
                ("registry_court", "registry_section", "registry_insert"),
                "insolvency_status",
            )
        }),
        ("Bankovní spojení", {
            "fields": (("bank_name", "bank_account", "bank_code"),)
        }),
        ("Kontakt", {
            "fields": (("contact_email", "contact_phone"),)
        }),
        ("Poznámka", {
            "fields": ("note",)
        }),
    )
    readonly_fields = ("ares_button", "insolvency_status")
    inlines = [ClientCardInline, ContractInline]
    actions = ["export_emaily"]

    @admin.display(description="Název", ordering="name")
    def name_display(self, obj):
        from django.utils.html import format_html
        if "v likvidaci" in obj.name.lower():
            return format_html('<span style="color:#dc2626; font-weight:600;">{}</span>', obj.name)
        return obj.name

    @admin.display(description="Insolvence", ordering="insolvency_status")
    def insolvency_display(self, obj):
        from django.utils.html import format_html
        if obj.insolvency_status == Client.InsolvencyStatus.ACTIVE:
            return format_html('<span style="color:#dc2626; font-weight:600;">⚠ Aktivní</span>')
        if obj.insolvency_status == Client.InsolvencyStatus.HISTORICAL:
            return format_html('<span style="color:#b45309;">Dříve</span>')
        return "—"

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
        ]
        return custom + urls

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


@admin.register(Contract)
class ContractAdmin(ModelAdmin):
    list_display = ("client", "number", "valid_from", "valid_to", "deposit_paid", "has_inflation_clause")
    list_filter = ("deposit_paid", "has_inflation_clause")
    search_fields = ("number", "client__name", "client__ico")
    autocomplete_fields = ("client", "site")
    actions = ["generate_document", "generovat_karty_inflace"]

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
        fill_contract_template(contract_to_template_data(contract), buf)
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


@admin.register(ClientCard)
class ClientCardAdmin(ModelAdmin):
    list_display = ("client", "description", "valid_from", "valid_to", "is_active")
    list_filter = ("client__is_active", "is_active")
    autocomplete_fields = ("client",)
    search_fields = ("client__name", "description")
    fieldsets = (
        ("Základní údaje", {
            "fields": (("client", "description"), ("valid_from", "valid_to"), "is_active", "note")
        }),
        ("Karta nájemce (Příloha č. 1)", {
            "fields": ("generate_card_button", "document")
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
        ]
        return custom + urls

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
    fields = ("period", "reading_date", "value", "is_estimate", "note")
    ordering = ("-period",)


@admin.register(Meter)
class MeterAdmin(ModelAdmin):
    list_display = (
        "code", "name", "site", "meter_type", "parent_meter",
        "reading_mode", "is_virtual", "unit_of_measure",
    )
    list_filter = ("site", "meter_type", "reading_mode", "is_virtual")
    search_fields = ("name", "code", "serial_number")
    autocomplete_fields = ("parent_meter",)
    inlines = [MeterReadingInline]
    fieldsets = (
        (None, {
            "fields": (("site", "code", "name"), ("meter_type", "unit_of_measure", "serial_number"))
        }),
        ("Odečty", {
            "fields": ("reading_mode",),
            "description": (
                "Vetsina meridel hlasi kumulativni Stav. Pokud dodavatel hlasi "
                "rovnou Spotrebu za obdobi (napr. hlavni odberne misto elektro), "
                "prepni na 'Spotreba za obdobi' - pak staci zadavat odecet jen "
                "za aktualni mesic, bez nutnosti znat predchozi stav."
            ),
        }),
        ("Hierarchie", {
            "fields": ("parent_meter",)
        }),
        ("Virtuální měřidlo", {
            "fields": (("is_virtual", "formula"),),
            "description": "Vyplnit pouze pokud se spotřeba nepočítá z odečtů, ale ze vzorce odkazujícího na kódy jiných měřidel (např. E_A1+E_AB1).",
        }),
    )

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
        ]
        return custom + urls


@admin.register(Period)
class PeriodAdmin(ModelAdmin):
    list_display = ("__str__", "status", "days_in_period")
    list_filter = ("status",)
    ordering = ("-year", "-month")
    actions = ["spocitat_rozuctovani", "uzavrit_obdobi", "znovu_otevrit_obdobi"]

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
        from billing.engine import BillingPeriodClosedError, calculate_period

        for period in queryset:
            label = f"{period} / {site}" if site else str(period)
            try:
                result = calculate_period(period, site=site)
            except BillingPeriodClosedError as e:
                self.message_user(request, str(e), level=messages.ERROR)
                continue
            text = f"{label}: vytvořeno {result['created']} vyúčtovaných položek."
            if result["warnings"]:
                text += " Varování: " + " | ".join(result["warnings"])
                self.message_user(request, text, level=messages.WARNING)
            else:
                self.message_user(request, text, level=messages.SUCCESS)

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


@admin.register(MeterReading)
class MeterReadingAdmin(ModelAdmin):
    list_display = ("meter", "period", "reading_date", "value", "is_estimate")
    list_filter = ("meter__site", "meter__meter_type", "period", "is_estimate")
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
    carka jako desetinny oddelovac)."""
    if value is None:
        return "-"
    text = f"{value:,.{decimals}f}"
    text = text.replace(",", "\x00").replace(".", ",").replace("\x00", " ")
    return f"{text} Kč"


@admin.register(ServicePoolItem)
class ServicePoolItemAdmin(ModelAdmin):
    list_display = (
        "name", "site", "invoice_class", "unit", "meter", "jednotka",
        "default_allocation_type", "default_amount_czk_display",
    )
    list_filter = ("site", "invoice_class")
    search_fields = ("name",)
    autocomplete_fields = ("unit", "meter")

    @admin.display(description="Jednotka")
    def jednotka(self, obj):
        return _jednotka_polozky(obj)

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
        "unit", "deduct_from_pool", "valid_from", "valid_to",
    )
    list_filter = ("allocation_type", "deduct_from_pool")
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
        return obj.value


@admin.register(PriceList)
class PriceListAdmin(ModelAdmin):
    list_display = ("service_item", "period", "price_per_unit_display", "note")
    list_filter = ("period", "service_item__site")
    autocomplete_fields = ("service_item",)
    search_fields = ("service_item__name",)

    @admin.display(description="Cena za jednotku (Kč)", ordering="price_per_unit")
    def price_per_unit_display(self, obj):
        return _format_kc(obj.price_per_unit, decimals=4)


@admin.register(CostEntry)
class CostEntryAdmin(ModelAdmin):
    list_display = (
        "service_item", "period", "amount_units", "jednotka", "kc_za_jednotku", "amount_czk_display",
    )
    list_filter = ("period", "service_item__site")
    autocomplete_fields = ("service_item",)

    @admin.display(description="Jednotka")
    def jednotka(self, obj):
        return _jednotka_polozky(obj.service_item)

    @admin.display(description="Kč/jednotka")
    def kc_za_jednotku(self, obj):
        """Efektivni cena za jednotku - primo z amount_czk/amount_units,
        pripadne (u merenych polozek bez primo zadaneho amount_czk)
        z aktualne platneho Ceniku pro dane obdobi."""
        if obj.amount_units:
            if obj.amount_czk is not None:
                try:
                    return _format_kc(obj.amount_czk / obj.amount_units, decimals=4)
                except (ZeroDivisionError, TypeError):
                    pass
            price = PriceList.get_price_for_period(obj.service_item, obj.period)
            if price is not None:
                return _format_kc(price, decimals=4)
        return "-"

    @admin.display(description="Částka (Kč)", ordering="amount_czk")
    def amount_czk_display(self, obj):
        return _format_kc(obj.amount_czk)


@admin.register(BillingLine)
class BillingLineAdmin(ModelAdmin):
    list_display = ("client_card_display", "service_item", "period", "amount_display", "share")
    list_filter = ("period",)
    search_fields = ("client_card__client__name",)
    readonly_fields = ("client_card_display", "period", "service_item", "amount", "share", "calc_detail")
    actions = ["generovat_vyuctovani_pdf"]

    @admin.display(description="Karta klienta", ordering="client_card")
    def client_card_display(self, obj):
        return obj.client_card.description or f"Karta {obj.client_card.client}"

    @admin.display(description="Částka (Kč)", ordering="amount")
    def amount_display(self, obj):
        return _format_kc(obj.amount)

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
