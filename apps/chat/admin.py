from django.contrib import admin

from apps.chat.models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "text", "image", "read_at", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "updated_at")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "conversation", "short_text", "is_read", "created_at")
    list_filter = ("read_at",)
    search_fields = ("sender__phone", "text")

    @admin.display(description="Matn")
    def short_text(self, obj):
        return obj.text[:50]
