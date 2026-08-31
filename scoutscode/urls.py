"""Public URL configuration for the retired ScoutsCode site."""

from django.urls import path, re_path
from django.views.generic import RedirectView, TemplateView


urlpatterns = [
    path(
        "",
        TemplateView.as_view(template_name="blog_index.html"),
        name="blog_index",
    ),
    re_path(
        r"^.*$",
        RedirectView.as_view(url="/", permanent=False),
        name="retired_site_redirect",
    ),
]
