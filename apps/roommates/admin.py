from django.contrib import admin

from apps.roommates.models import Match, RoommateProfile


@admin.register(RoommateProfile)
class RoommateProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "looking_for", "budget_min", "budget_max", "is_active", "created_at")
    list_filter = ("is_active", "looking_for", "city", "smoking", "pets")
    search_fields = ("user__phone", "city")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("user_a", "user_b", "score", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("user_a__phone", "user_b__phone")
