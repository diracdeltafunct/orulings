class AuthenticatedHeaderMiddleware:
    """Add X-Authenticated header so the service worker can avoid caching admin pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if hasattr(request, "user") and request.user.is_authenticated:
            response["X-Authenticated"] = "true"
        return response
