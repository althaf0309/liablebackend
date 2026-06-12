import logging

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrStaff
from .models import (
    VisitorSession,
    PageView,
    ClickEvent,
    PropertySearchHistory,
)

logger = logging.getLogger(__name__)

_DAYS_DEFAULT = 30


def _days_param(request, default=_DAYS_DEFAULT, max_val=90):
    try:
        d = int(request.query_params.get("days", default))
        return min(max(1, d), max_val)
    except (TypeError, ValueError):
        return default


class AnalyticsSummaryView(APIView):
    """Overall traffic summary — visitors, page views, top pages, top search terms."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        days = _days_param(request)
        since = timezone.now() - timezone.timedelta(days=days)

        total_sessions = VisitorSession.objects.filter(first_seen_at__gte=since).count()
        total_pageviews = PageView.objects.filter(created_at__gte=since).count()

        top_pages = (
            PageView.objects.filter(created_at__gte=since)
            .values("path")
            .annotate(views=Count("id"))
            .order_by("-views")[:10]
        )

        top_searches = (
            PropertySearchHistory.objects.filter(created_at__gte=since)
            .exclude(query_text="")
            .values("query_text")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        daily_sessions = (
            VisitorSession.objects.filter(first_seen_at__gte=since)
            .annotate(day=TruncDate("first_seen_at"))
            .values("day")
            .annotate(sessions=Count("id"))
            .order_by("day")
        )

        return Response({
            "days": days,
            "total_sessions": total_sessions,
            "total_pageviews": total_pageviews,
            "top_pages": list(top_pages),
            "top_searches": list(top_searches),
            "daily_sessions": [
                {"day": str(r["day"]), "sessions": r["sessions"]}
                for r in daily_sessions
            ],
        })


class AnalyticsClicksView(APIView):
    """Click event breakdown by type."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        days = _days_param(request)
        since = timezone.now() - timezone.timedelta(days=days)

        by_type = (
            ClickEvent.objects.filter(created_at__gte=since)
            .values("event_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        property_clicks = (
            ClickEvent.objects.filter(
                created_at__gte=since,
                event_type="PROPERTY_CARD_CLICK",
                property_id__isnull=False,
            )
            .values("property_id")
            .annotate(clicks=Count("id"))
            .order_by("-clicks")[:10]
        )

        return Response({
            "days": days,
            "by_type": list(by_type),
            "top_property_clicks": [
                {"property_id": str(r["property_id"]), "clicks": r["clicks"]}
                for r in property_clicks
            ],
        })


class AnalyticsSearchView(APIView):
    """Property search behaviour analytics."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        days = _days_param(request)
        since = timezone.now() - timezone.timedelta(days=days)

        qs = PropertySearchHistory.objects.filter(created_at__gte=since)

        total = qs.count()
        zero_results = qs.filter(results_count=0).count()
        enquiry_rate = qs.filter(enquiry_submitted=True).count()

        top_terms = (
            qs.exclude(query_text="")
            .values("query_text")
            .annotate(count=Count("id"))
            .order_by("-count")[:15]
        )

        return Response({
            "days": days,
            "total_searches": total,
            "zero_result_searches": zero_results,
            "searches_leading_to_enquiry": enquiry_rate,
            "top_terms": list(top_terms),
        })


class AnalyticsPageViewTrackView(APIView):
    """Public endpoint — frontend sends page view tracking events."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        from .models import VisitorSession, PageView
        from accounts.utils import get_client_ip

        ip = get_client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")[:500]
        path = request.data.get("path", "")[:500]
        full_url = request.data.get("full_url", "")[:1000]
        referrer = request.data.get("referrer", "")[:500]
        page_type = request.data.get("page_type", "OTHER")
        property_id = request.data.get("property_id")
        blog_post_id = request.data.get("blog_post_id")

        utm = {
            "utm_source": request.data.get("utm_source", "")[:120],
            "utm_medium": request.data.get("utm_medium", "")[:120],
            "utm_campaign": request.data.get("utm_campaign", "")[:120],
        }

        session, _ = VisitorSession.objects.get_or_create(
            ip_address=ip,
            user=request.user if request.user.is_authenticated else None,
            defaults={"user_agent": ua, **utm},
        )
        session.last_seen_at = timezone.now()
        session.save(update_fields=["last_seen_at"])

        PageView.objects.create(
            session=session,
            user=request.user if request.user.is_authenticated else None,
            path=path,
            full_url=full_url,
            referrer=referrer,
            page_type=page_type,
            property_id=property_id or None,
            blog_post_id=blog_post_id or None,
        )
        return Response({"ok": True})
