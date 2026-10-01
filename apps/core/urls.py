from django.urls import path

from apps.core.views import LanguagesView

app_name = "i18n"

urlpatterns = [
    path("languages/", LanguagesView.as_view(), name="languages"),
]