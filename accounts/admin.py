from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Role a klient", {"fields": ("role", "client")}),
    )
    list_display = ("username", "email", "role", "client", "is_active")
    list_filter = ("role", "is_active")
