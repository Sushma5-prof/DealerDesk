from django.http import JsonResponse
from django.shortcuts import render


def health(request):
    """GET /api/health/ — the grader polls this until your app is ready."""
    return JsonResponse({"status": "ok"})


def portal(request):
    """GET / — Interactive DealerDesk Portal talking exclusively to /api/*."""
    return render(request, "core/portal.html")
