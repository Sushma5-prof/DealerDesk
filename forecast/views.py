from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class ForecastDetailView(APIView):
    """GET /api/forecast/{sku}/"""

    def get(self, request, sku: str):
        data = services.get_sku_forecast(sku)
        return Response(data, status=status.HTTP_200_OK)


class ReorderSuggestionsView(APIView):
    """GET /api/reorder-suggestions/"""

    def get(self, request):
        results = services.get_reorder_suggestions()
        return Response({"results": results}, status=status.HTTP_200_OK)
