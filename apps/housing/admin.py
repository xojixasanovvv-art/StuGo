from django.contrib import admin

from apps.housing.models import Amenity, Favorite, Listing, ListingImage


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 1


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "city", "type", "price", "currency", "status", "created_at")
    list_filter = ("status", "type", "currency", "city")
    search_fields = ("title", "owner__phone", "city", "district")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ListingImageInline]


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")
    search_fields = ("name",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "listing", "created_at")
    search_fields = ("user__phone", "listing__title")
