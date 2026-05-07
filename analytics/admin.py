# analytics/admin.py
from django.contrib import admin
from .models import *


@admin.register(VisitorSession)
class VisitorSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "ip_address", "first_seen_at", "last_seen_at", "utm_source", "utm_campaign")
    list_filter = ("first_seen_at", "utm_source", "utm_medium", "utm_campaign")
    search_fields = ("id", "user__email", "ip_address", "user_agent")
    readonly_fields = ("id", "first_seen_at", "last_seen_at")
    ordering = ("-first_seen_at",)


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ("created_at", "page_type", "path", "session", "user", "property_id", "blog_post_id")
    list_filter = ("page_type", "created_at")
    search_fields = ("path", "referrer", "full_url", "session__id", "user__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ClickEvent)
class ClickEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "label", "target_url", "session", "user", "property_id", "blog_post_id")
    list_filter = ("event_type", "created_at")
    search_fields = ("label", "target_url", "session__id", "user__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PropertySearchHistory)
class PropertySearchHistoryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "session", "user", "query_text", "results_count", "enquiry_submitted", "clicked_property_id")
    list_filter = ("created_at", "enquiry_submitted")
    search_fields = ("query_text", "session__id", "user__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "opened_at", "closed_at", "channel", "visitor_session", "user")
    list_filter = ("opened_at", "channel")
    search_fields = ("id", "visitor_session__id", "user__email")
    readonly_fields = ("id", "opened_at", "closed_at")
    ordering = ("-opened_at",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "sender", "intent", "confidence", "chat_session")
    list_filter = ("sender", "intent", "created_at")
    search_fields = ("text", "intent", "chat_session__id")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
