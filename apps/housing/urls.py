from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.housing import views

router = DefaultRouter()
router.register("listings", views.ListingViewSet, basename="listings")

urlpatterns = [
    path("", include(router.urls)),
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
]
