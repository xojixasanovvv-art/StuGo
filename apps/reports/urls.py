from django.urls import path

from apps.reports import views

urlpatterns = [
    path("reports/", views.ReportListCreateView.as_view(), name="reports"),
    path("reports/mine/", views.ReportListCreateView.as_view(), name="my-reports"),
    path("users/blocks/", views.BlockListCreateView.as_view(), name="blocks"),
    path("admin/reports/", views.ReportModerationListView.as_view(), name="report-moderation"),
    path(
        "admin/reports/<int:pk>/decision/",
        views.ReportDecisionView.as_view(),
        name="report-decision",
    ),
]
