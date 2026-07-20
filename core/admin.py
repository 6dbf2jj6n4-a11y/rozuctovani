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
    Meter, MeterReading, Period,
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
    model = Contract
    extra = 0
    fields = ("number_link", "valid_from", "valid_to", "signed_on", "deposit_paid", "has_inflation_clause")
    readonly_fields = ("number_link",)
    verbose_name = "Smlouva"
    verbose_name_plural = "Smlouvy"

    def number_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse("admin:core_contract_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.number or "—")
    number_link.short_description = "Číslo smlouvy"


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


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "code", "ico", "contact_email", "contact_phone", "is_active", "is_landlord")
    search_fields = ("name", "ico", "code")
    list_filter = ("is_active", "is_landlord", SiteFilter)
    fieldsets = (
        ("Základní údaje", {
            "fields": (("name", "code"), ("is_active", "is_landlord"))
        }),
        ("Sídlo", {
            "fields": (("street", "street_number"), ("zip_code", "city"))
        }),
        ("Identifikace", {
            "fields": (("ico", "dic", "ares_button"), "vat_payer", ("registry_court", "registry_section", "registry_insert"))
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
    readonly_fields = ("ares_button",)
    inlines = [ClientCardInline, ContractInline]
    actions = ["export_emaily"]

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
            client = Client.objects.filter(ico=ico).first()
            if client:
                return JsonResponse({
                    "exists": True,
                    "name": client.name,
                    "url": f"/admin/core/client/{client.pk}/change/",
                })
            return JsonResponse({"exists": False})

        urls = super().get_urls()
        custom = [
            path("ico-lookup/", self.admin_site.admin_view(ico_lookup), name="core_client_ico_lookup"),
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
    actions = ["generate_document"]

    @admin.action(description="Vygenerovat dokument smlouvy (.docx)")
    def generate_document(self, request, queryset):
        from io import BytesIO
        from django.core.files.base import ContentFile
        from core.contract_generator import fill_contract_template

        generated, skipped = 0, []
        for contract in queryset:
            client = contract.client
            address = " ".join(p for p in (client.street, client.street_number) if p)
            if client.zip_code or client.city:
                address = f"{address}, {client.zip_code} {client.city}".strip(", ")

            data = {
                "site_name": str(contract.site) if contract.site else "",
                "client_name": client.name,
                "client_address": address,
                "client_ico": client.ico,
                "client_dic": client.dic,
                "registry_court": client.registry_court,
                "registry_section": client.registry_section,
                "registry_insert": client.registry_insert,
                "representative_name": contract.representative_name,
                "representative_role": contract.representative_role,
                "invoicing_email": contract.invoicing_email,
                "signed_on": contract.signed_on,
                "valid_from": contract.valid_from,
                "notice_period_months": contract.notice_period_months,
                "insurance_amount_czk": contract.insurance_amount_czk,
                "deposit_czk": contract.deposit_czk,
                "inflation_increase_from": contract.inflation_increase_from,
            }
            try:
                buf = BytesIO()
                fill_contract_template(data, buf)
            except Exception as exc:
                skipped.append(f"{contract}: {exc}")
                continue
            filename = f"smlouva_{client.code or client.pk}_{contract.pk}.docx"
            contract.document.save(filename, ContentFile(buf.getvalue()), save=True)
            generated += 1

        text = f"Vygenerováno {generated} dokumentů."
        if skipped:
            text += " Přeskočeno: " + " | ".join(skipped)
            self.message_user(request, text, level=messages.WARNING)
        else:
            self.message_user(request, text, level=messages.SUCCESS)

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
            "fields": ("document",)
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
    )

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
            units = list(card.card_units.all())
            new_card = ClientCard(
                client=card.client,
                unit=card.unit,
                valid_from=card.valid_from,
                valid_to=card.valid_to,
                note=card.note,
                description=f"{card.description} (kopie)",
                external_id=None,
                is_active=False,
            )
            new_card.save()
            for cu in units:
                CardUnit.objects.create(card=new_card, unit=cu.unit)
        self.message_user(request, f"Vytvořeno {queryset.count()} kopií karet.")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path("kopie/<int:card_id>/", self.admin_site.admin_view(self.kopie_view), name="core_clientcard_kopie"),
        ]
        return custom + urls

    def kopie_view(self, request, card_id):
        from django.shortcuts import redirect
        original = ClientCard.objects.get(pk=card_id)
        units = list(original.card_units.all())
        new_card = ClientCard(
            client=original.client,
            unit=original.unit,
            valid_from=original.valid_from,
            valid_to=original.valid_to,
            note=original.note,
            description=f"{original.description} (kopie)",
            external_id=None,
            is_active=False,
        )
        new_card.save()
        for cu in units:
            CardUnit.objects.create(card=new_card, unit=cu.unit)
        self.message_user(request, "Kopie karty byla vytvořena.")
        return redirect(f"/admin/core/clientcard/{new_card.pk}/change/")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["kopie_url"] = f"/admin/core/clientcard/kopie/{object_id}/"
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
    actions = ["spocitat_rozuctovani"]

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
        from billing.engine import calculate_period

        for period in queryset:
            result = calculate_period(period, site=site)
            label = f"{period} / {site}" if site else str(period)
            text = f"{label}: vytvořeno {result['created']} vyúčtovaných položek."
            if result["warnings"]:
                text += " Varování: " + " | ".join(result["warnings"])
                self.message_user(request, text, level=messages.WARNING)
            else:
                self.message_user(request, text, level=messages.SUCCESS)


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


@admin.register(ServicePoolItem)
class ServicePoolItemAdmin(ModelAdmin):
    list_display = (
        "name", "site", "invoice_class", "unit", "meter", "jednotka",
        "default_allocation_type", "default_amount_czk",
    )
    list_filter = ("site", "invoice_class")
    search_fields = ("name",)
    autocomplete_fields = ("unit", "meter")

    @admin.display(description="Jednotka")
    def jednotka(self, obj):
        return _jednotka_polozky(obj)

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
        "client_card_display", "service_item", "allocation_type", "value",
        "unit", "deduct_from_pool", "valid_from", "valid_to",
    )
    list_filter = ("allocation_type", "deduct_from_pool")
    autocomplete_fields = ("client_card", "service_item", "meter", "unit")

    @admin.display(description="Karta klienta", ordering="client_card")
    def client_card_display(self, obj):
        return obj.client_card.description or f"Karta {obj.client_card.client}"


@admin.register(PriceList)
class PriceListAdmin(ModelAdmin):
    list_display = ("service_item", "period", "price_per_unit", "note")
    list_filter = ("period", "service_item__site")
    autocomplete_fields = ("service_item",)
    search_fields = ("service_item__name",)


@admin.register(CostEntry)
class CostEntryAdmin(ModelAdmin):
    list_display = (
        "service_item", "period", "amount_units", "jednotka", "kc_za_jednotku", "amount_czk",
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
                    return round(obj.amount_czk / obj.amount_units, 2)
                except (ZeroDivisionError, TypeError):
                    pass
            price = PriceList.get_price_for_period(obj.service_item, obj.period)
            if price is not None:
                return round(price, 4)
        return "-"


@admin.register(BillingLine)
class BillingLineAdmin(ModelAdmin):
    list_display = ("client_card_display", "service_item", "period", "amount", "share")
    list_filter = ("period",)
    readonly_fields = ("client_card_display", "period", "service_item", "amount", "share", "calc_detail")

    @admin.display(description="Karta klienta", ordering="client_card")
    def client_card_display(self, obj):
        return obj.client_card.description or f"Karta {obj.client_card.client}"

    def has_add_permission(self, request):
        return False
