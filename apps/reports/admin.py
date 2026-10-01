from django.contrib import admin

from apps.reports.models import Block, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reporter", "target_type", "target_id", "reason", "status", "created_at")
    list_filter = ("status", "reason", "target_type")
    search_fields = ("reporter__phone", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    search_fields = ("blocker__phone", "blocked__phone")
