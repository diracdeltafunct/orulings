def client_ip(request):
    """
    Client IP for django-ratelimit behind a reverse proxy.

    Prefers the first X-Forwarded-For hop, then X-Real-IP, then REMOTE_ADDR
    (empty when the proxy connects over a Unix socket).
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")
