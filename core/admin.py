from django.contrib import admin

from .models import Client, ClientCard, Site, Unit


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "address")
    inlines = [UnitInline]


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "area_m2")
    list_filter = ("site",)
    search_fields = ("name",)


class ClientCardInline(admin.TabularInline):
    model = ClientCard
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "ico", "contact_email", "contact_phone")
    search_fields = ("name", "ico")
    inlines = [ClientCardInline]


@admin.register(ClientCard)
class ClientCardAdmin(admin.ModelAdmin):
    list_display = ("client", "unit", "valid_from", "valid_to")
    list_filter = ("unit__site",)
    autocomplete_fields = ("client", "unit")
    search_fields = ("client__name", "unit__name")
