from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Contract §3: paginated lists use page (1-based) and page_size (default 20, max 100).
    Response shape: {"count": N, "next": "...", "previous": null, "results": [...]}
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"
