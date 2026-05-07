# analytics/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings


class VisitorSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    utm_source = models.CharField(max_length=120, blank=True)
    utm_medium = models.CharField(max_length=120, blank=True)
    utm_campaign = models.CharField(max_length=120, blank=True)

    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["first_seen_at"]),
            models.Index(fields=["ip_address"]),
        ]


class PageView(models.Model):
    PAGE_TYPES = [
        ("HOME", "Home"),
        ("SEARCH", "Search"),
        ("PROPERTY", "Property Detail"),
        ("BLOG_LIST", "Blog List"),
        ("BLOG_DETAIL", "Blog Detail"),
        ("CONTACT", "Contact"),
        ("OTHER", "Other"),
    ]

    id = models.BigAutoField(primary_key=True)

    session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name="page_views")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    path = models.CharField(max_length=500)
    full_url = models.TextField(blank=True)
    referrer = models.CharField(max_length=500, blank=True)

    page_type = models.CharField(max_length=20, choices=PAGE_TYPES, default="OTHER")

    property_id = models.UUIDField(null=True, blank=True)
    blog_post_id = models.UUIDField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["page_type"]),
            models.Index(fields=["path"]),
        ]


class ClickEvent(models.Model):
    EVENT_TYPES = [
        ("PROPERTY_CARD_CLICK", "Property Card Click"),
        ("PROPERTY_ENQUIRE_CLICK", "Property Enquire Click"),
        ("BLOG_CARD_CLICK", "Blog Card Click"),
        ("FILTER_APPLY", "Filter Apply"),
        ("SORT_CHANGE", "Sort Change"),
        ("NAV_CLICK", "Nav Click"),
        ("CHATBOT_OPEN", "Chatbot Open"),
    ]

    id = models.BigAutoField(primary_key=True)

    session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name="clicks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    event_type = models.CharField(max_length=60, choices=EVENT_TYPES)
    label = models.CharField(max_length=200, blank=True)
    target_url = models.TextField(blank=True)

    property_id = models.UUIDField(null=True, blank=True)
    blog_post_id = models.UUIDField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["event_type"]),
        ]


class PropertySearchHistory(models.Model):
    id = models.BigAutoField(primary_key=True)

    session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name="property_searches")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    query_text = models.CharField(max_length=300, blank=True)
    filters = models.JSONField(default=dict, blank=True)  # store all filters
    sort = models.CharField(max_length=60, blank=True)

    center_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_km = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    results_count = models.IntegerField(default=0)
    shown_property_ids = models.JSONField(default=list, blank=True)  # first page IDs
    total_pages = models.IntegerField(default=0)

    clicked_property_id = models.UUIDField(null=True, blank=True)
    enquiry_submitted = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["results_count"]),
            models.Index(fields=["enquiry_submitted"]),
        ]


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    visitor_session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name="chat_sessions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    channel = models.CharField(max_length=30, default="web")
    locale = models.CharField(max_length=10, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["opened_at"]),
            models.Index(fields=["channel"]),
        ]


class ChatMessage(models.Model):
    id = models.BigAutoField(primary_key=True)

    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")

    sender = models.CharField(max_length=10, choices=[("user", "User"), ("bot", "Bot")])
    text = models.TextField()

    intent = models.CharField(max_length=120, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    extracted_filters = models.JSONField(default=dict, blank=True)

    linked_property_search = models.ForeignKey(
        PropertySearchHistory, null=True, blank=True, on_delete=models.SET_NULL, related_name="chat_messages"
    )

    recommended_property_ids = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["sender"]),
            models.Index(fields=["intent"]),
        ]
