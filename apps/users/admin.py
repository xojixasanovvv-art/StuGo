from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import Profile, TelegramLinkCode, User, VerificationRequest


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    readonly_fields = ("telegram_id", "telegram_username", "telegram_linked_at")
    fields = (
        "full_name",
        "avatar",
        "birth_date",
        "gender",
        "city",
        "university",
        "faculty",
        "course",
        "bio",
        "languages",
        "interests",
        "telegram_id",
        "telegram_username",
        "telegram_linked_at",
    )


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("phone", "email", "role", "is_verified", "is_active", "date_joined")
    list_filter = ("role", "is_verified", "is_active")
    search_fields = ("phone", "email")
    ordering = ("-date_joined",)
    inlines = [ProfileInline]

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Shaxsiy", {"fields": ("email", "role", "gender", "is_verified")}),
        ("Ruxsatlar", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Muhim sanalar", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "password1", "password2")}),
    )


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "method", "status", "created_at", "reviewed_by")
    list_filter = ("status", "method")
    search_fields = ("user__phone", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TelegramLinkCode)
class TelegramLinkCodeAdmin(admin.ModelAdmin):
    """Bog'lanish kodlari — odatda avtomatik tozalanadi, lekin qo'lda
    ham ko'rish/tuzatish mumkin bo'lishi kerak (muammolarni izlashda)."""

    list_display = ("code", "user", "expires_at", "used_at", "attempts", "created_at")
    list_filter = ("used_at",)
    search_fields = ("code", "user__phone", "user__email")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
