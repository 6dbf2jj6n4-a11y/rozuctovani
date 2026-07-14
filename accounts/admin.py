from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User as AuthUser
from unfold.admin import ModelAdmin
from .models import User

try:
    admin.site.unregister(AuthUser)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class CustomUserAdmin(ModelAdmin, UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Role a klient", {"fields": ("role", "client")}),
    )
    list_display = ("username", "email", "role", "client", "is_active")
    list_filter = ("role", "is_active")
