from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class SupplierSyncView(APIView):
    """POST /api/sync/supplier/"""

    def post(self, request):
        result = services.run_supplier_sync()
        return Response(result, status=status.HTTP_200_OK)
