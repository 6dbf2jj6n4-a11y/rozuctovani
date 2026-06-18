from django.contrib import admin
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


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "code", "ico", "contact_email", "contact_phone", "is_active")
    search_fields = ("name", "ico", "code")
    list_filter = ("is_active",)
    inlines = [ClientCardInline]


@admin.register(ClientCard)
class ClientCardAdmin(ModelAdmin):
    list_display = ("client", "description", "valid_from", "valid_to")
    list_filter = ("client__is_active",)
    autocomplete_fields = ("client",)
    search_fields = ("client__name", "description")
    inlines = [CardUnitInline]


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
