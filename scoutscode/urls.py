"""
URL configuration for scoutscode project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('app/', include('app.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from post.views import (
    blog_index,
    card_detail,
    card_search,
    contact,
    core_rules,
    crsection_detail,
    post_detail,
    post_list,
    save_annotation,
    search_rules,
    secret_login,
    trsection_detail,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("mdeditor/", include("mdeditor.urls")),
    path("", blog_index, name="blog_index"),
    path("posts/", post_list, name="post_list"),
    path("posts/<int:post_id>/", post_detail, name="post_detail"),
    path("trsections/<str:section>/", trsection_detail, name="trsection_detail"),
    path("crsections/<str:section>/", crsection_detail, name="crsection_detail"),
    path("core-rules/", core_rules, name="core_rules"),
    path("search/", search_rules, name="search_rules"),
    path("secretadminlogin/", secret_login, name="secret_login"),
    path("api/save-annotation/", save_annotation, name="save_annotation"),
    path("contact/", contact, name="contact"),
    path("cards/", card_search, name="card_search"),
    path("cards/<str:card_id>/", card_detail, name="card_detail"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
