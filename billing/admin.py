from django.contrib import admin

from .models import AllocationKey, BillingLine, CostEntry, ServicePoolItem


class AllocationKeyInline(admin.TabularInline):
    model = AllocationKey
    extra = 0
    autocomplete_fields = ("client_card", "meter")


@admin.register(ServicePoolItem)
class ServicePoolItemAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "invoice_class", "unit", "meter")
    list_filter = ("site", "invoice_class")
    search_fields = ("name",)
    autocomplete_fields = ("unit", "meter")
    inlines = [AllocationKeyInline]


@admin.register(AllocationKey)
class AllocationKeyAdmin(admin.ModelAdmin):
    list_display = ("client_card", "service_item", "allocation_type", "value", "meter", "valid_from", "valid_to")
    list_filter = ("allocation_type", "service_item__site")
    autocomplete_fields = ("client_card", "service_item", "meter")


@admin.register(CostEntry)
class CostEntryAdmin(admin.ModelAdmin):
    list_display = ("service_item", "period", "amount")
    list_filter = ("period", "service_item__site")
    autocomplete_fields = ("service_item",)


@admin.register(BillingLine)
class BillingLineAdmin(admin.ModelAdmin):
    list_display = ("client_card", "service_item", "invoice_class", "period", "amount", "share")
    list_filter = ("period", "service_item__invoice_class", "service_item__site")
    readonly_fields = ("client_card", "period", "service_item", "amount", "share", "calc_detail")

    def has_add_permission(self, request):
        # Radky vznikaji vypoctem (billing.engine.calculate_period), ne rucne.
        return False

    @admin.display(description="Třída")
    def invoice_class(self, obj):
        return obj.service_item.get_invoice_class_display()
