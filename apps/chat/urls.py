from django.urls import path

from apps.chat import views

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view(), name="conversations"),
    path(
        "conversations/<int:pk>/messages/",
        views.MessageListView.as_view(),
        name="conversation-messages",
    ),
]
