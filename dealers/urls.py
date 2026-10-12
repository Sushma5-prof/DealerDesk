from django.urls import path
from . import views

urlpatterns = [
    path("dealers/", views.DealerListCreateView.as_view(), name="dealer-list-create"),
    path("dealers/<int:dealer_id>/", views.DealerDetailView.as_view(), name="dealer-detail"),
]
