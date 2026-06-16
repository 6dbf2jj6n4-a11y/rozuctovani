from django.contrib import admin, messages

from .models import Meter, MeterReading, Period


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "days_in_period")
    list_filter = ("status",)
    ordering = ("-year", "-month")
    actions = ["run_calculation"]

    @admin.action(description="Spočítat rozúčtování za vybraná období")
    def run_calculation(self, request, queryset):
        from billing.engine import calculate_period

        for period in queryset:
            result = calculate_period(period)
            self.message_user(
                request,
                f"{period}: vytvořeno {result['created']} položek vyúčtování.",
                level=messages.SUCCESS,
            )
            for warning in result["warnings"]:
                self.message_user(request, f"{period}: {warning}", level=messages.WARNING)


@admin.register(Meter)
class MeterAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "meter_type", "parent_meter", "unit_of_measure")
    list_filter = ("site", "meter_type")
    search_fields = ("name", "serial_number")
    autocomplete_fields = ("parent_meter",)


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("meter", "period", "reading_date", "value", "is_estimate")
    list_filter = ("period", "meter__site", "is_estimate")
    autocomplete_fields = ("meter",)
