from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "is_read", "created_at")
    list_filter = ("type", "is_read")
    search_fields = ("user__phone",)
    readonly_fields = ("created_at", "updated_at")
