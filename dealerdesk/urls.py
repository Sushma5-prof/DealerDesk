from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Core: health check
    path("api/", include("core.urls")),
    # B1: Products + Inventory
    path("api/", include("catalogue.urls")),
    # B2: Dealers
    # path("api/", include("dealers.urls")),
    # B3: Orders
    # path("api/", include("orders.urls")),
    # B4: Supplier sync
    # path("api/", include("supplier_sync.urls")),
    # B5: Dealer Assistant
    # path("api/", include("assistant.urls")),
    # B6: Forecast + Reorder
    # path("api/", include("forecast.urls")),
]
