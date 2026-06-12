from django.urls import path
from .views import (
    AnalyticsSummaryView,
    AnalyticsClicksView,
    AnalyticsSearchView,
    AnalyticsPageViewTrackView,
)

urlpatterns = [
    path("summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("clicks/", AnalyticsClicksView.as_view(), name="analytics-clicks"),
    path("search/", AnalyticsSearchView.as_view(), name="analytics-search"),
    path("track/pageview/", AnalyticsPageViewTrackView.as_view(), name="analytics-track-pageview"),
]
