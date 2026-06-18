from django.contrib import admin
from django.db import models
from django.forms import TextInput, Textarea
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Client, ClientCard, Site, Unit, CardUnit,
    Meter, MeterReading, Period,
    ServicePoolItem, AllocationKey, CostEntry, BillingLine
)


class UnitInline(TabularInline):
    model = Unit
    extra = 0


@admin.register(Site)
class SiteAdmin(ModelAdmin):
    list_display = ("name", "address")
    inlines = [UnitInline]


@admin.register(Unit)
class UnitAdmin(ModelAdmin):
    list_display = ("code", "name", "site", "purpose", "area_m2", "unit_type")
    list_filter = ("site",)
    search_fields = ("name", "code")


class CardUnitInline(TabularInline):
    model = CardUnit
    extra = 0
    autocomplete_fields = ("unit",)


class ClientCardInline(TabularInline):
    model = ClientCard
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


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "code", "ico", "contact_email", "contact_phone", "is_active")
    search_fields = ("name", "ico", "code")
    list_filter = ("is_active",)
    fieldsets = (
        ("Základní údaje", {
            "fields": (("name", "code"), ("is_active",))
        }),
        ("Sídlo", {
            "fields": (("street", "street_number"), ("zip_code", "city"))
        }),
        ("Identifikace", {
            "fields": (("ico", "dic"), "vat_payer")
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
    inlines = [ClientCardInline]


@admin.register(ClientCard)
class ClientCardAdmin(ModelAdmin):
    list_display = ("client", "description", "valid_from", "valid_to")
    list_filter = ("client__is_active",)
    autocomplete_fields = ("client",)
    search_fields = ("client__name", "description")
    fieldsets = (
        ("Základní údaje", {
            "fields": (("client", "description"), ("valid_from", "valid_to"), "is_active", "note")
        }),
    )
    inlines = [CardUnitInline]
    actions = ["kopie_karty"]

    @admin.action(description="Vytvořit kopii vybraných karet")
    def kopie_karty(self, request, queryset):
        for card in queryset:
            units = list(card.card_units.all())
            card.pk = None
            card.description = f"{card.description} (kopie)"
            card.external_id = None
            card.is_active = False
            card.save()
            for cu in units:
                CardUnit.objects.create(card=card, unit=cu.unit)
        self.message_user(request, f"Vytvořeno {queryset.count()} kopií karet.")

   def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["kopie_url"] = f"/admin/core/clientcard/kopie/{object_id}/"
        return super().change_view(request, object_id, form_url, extra_context)

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


@admin.register(CardUnit)
class CardUnitAdmin(ModelAdmin):
    list_display = ("card", "unit")
    autocomplete_fields = ("card", "unit")


@admin.register(Meter)
class MeterAdmin(ModelAdmin):
    list_display = ("name", "site", "meter_type", "parent_meter", "unit_of_measure")
    list_filter = ("site", "meter_type")
    search_fields = ("name", "serial_number")
    autocomplete_fields = ("parent_meter",)


@admin.register(Period)
class PeriodAdmin(ModelAdmin):
    list_display = ("__str__", "status", "days_in_period")
    list_filter = ("status",)
    ordering = ("-year", "-month")


@admin.register(MeterReading)
class MeterReadingAdmin(ModelAdmin):
    list_display = ("meter", "period", "reading_date", "value", "is_estimate")
    list_filter = ("period", "meter__site", "is_estimate")
    autocomplete_fields = ("meter",)


@admin.register(ServicePoolItem)
class ServicePoolItemAdmin(ModelAdmin):
    list_display = ("name", "site", "invoice_class", "unit", "meter")
    list_filter = ("site", "invoice_class")
    search_fields = ("name",)
    autocomplete_fields = ("unit", "meter")


@admin.register(AllocationKey)
class AllocationKeyAdmin(ModelAdmin):
    list_display = ("client_card", "service_item", "allocation_type", "value", "valid_from", "valid_to")
    list_filter = ("allocation_type",)
    autocomplete_fields = ("client_card", "service_item", "meter")


@admin.register(CostEntry)
class CostEntryAdmin(ModelAdmin):
    list_display = ("service_item", "period", "amount")
    list_filter = ("period",)
    autocomplete_fields = ("service_item",)


@admin.register(BillingLine)
class BillingLineAdmin(ModelAdmin):
    list_display = ("client_card", "service_item", "period", "amount", "share")
    list_filter = ("period",)
    readonly_fields = ("client_card", "period", "service_item", "amount", "share", "calc_detail")

    def has_add_permission(self, request):
        return False
