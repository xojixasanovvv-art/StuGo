from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.housing import views

router = DefaultRouter()
router.register("listings", views.ListingViewSet, basename="listings")

# MUHIM: `path("", include(router.urls))` ROUTERDAN OLDIN bo'lishi kerak.
#
# Sababi: router `listings/<pk>/` uchun regex'ni `[^/.]+` bilan yaratadi, ya'ni
# `listings/mine/` ham unga mos keladi va `pk="mine"` bo'lib qoladi. Keyin
# `get_object()` `pk='mine'` ni `int()` ga aylantirishga urinib, `ValueError`
# beradi va foydalanuvchi `404 Not found` oladi — xato, ayniqsa endpoint
# mavjudligi kodda aniq ko'rinib turib turib.
#
# `listings/mine/` routerdan keyin yozilgan edi, shuning uchun hech qachon
# ishga tushmagan. Aniq yo'llar ro'yxatda `include(router.urls)` dan OLDIN
# kelishi kerak — router o'zidan keyingi qoldiqlarni `catch-all` sifatida
# ushlab oladi.
urlpatterns = [
    path("listings/mine/", views.MyListingsView.as_view(), name="my-listings"),
    path(
        "listings/<int:listing_pk>/images/",
        views.ListingImageViewSet.as_view({"post": "create"}),
        name="listing-images",
    ),
    path(
        "listings/<int:listing_pk>/images/<int:pk>/",
        views.ListingImageViewSet.as_view({"delete": "destroy"}),
        name="listing-image-delete",
    ),
    path("amenities/", views.AmenityListView.as_view(), name="amenities"),
    path(
        "admin/listings/moderation/",
        views.ListingModerationListView.as_view(),
        name="listing-moderation",
    ),
    # Oxirida — router. Uning `listings/<pk>/` va `listings/` qismlari
    # yuqoridagi aniq yo'llarni allaqach ushlagan bo'ladi.
    path("", include(router.urls)),
]