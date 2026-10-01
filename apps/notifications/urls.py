from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path(
        "notifications/<int:pk>/read/",
        views.NotificationReadView.as_view(),
        name="notification-read",
    ),
]
