from django.urls import path

from apps.roommates import views

urlpatterns = [
    path("roommates/profile/", views.RoommateProfileView.as_view(), name="roommate-profile"),
    path("roommates/matches/", views.MatchListView.as_view(), name="roommate-matches"),
    path(
        "roommates/matches/request/",
        views.MatchRequestView.as_view(),
        name="roommate-match-request",
    ),
    path(
        "roommates/matches/<int:pk>/decision/",
        views.MatchDecisionView.as_view(),
        name="roommate-decision",
    ),
]
