"""
URL configuration for blog project.

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
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.urls import re_path as url

from post.views import (
    blog_index,
    crsection_detail,
    post_detail,
    post_list,
    save_annotation,
    secret_login,
    trsection_detail,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    url(r"mdeditor/", include("mdeditor.urls")),
    url(r"^$", blog_index, name="blog_index"),
    path("posts/", post_list, name="post_list"),
    path("posts/<int:post_id>/", post_detail, name="post_detail"),
    path("trsections/<str:section>/", trsection_detail, name="trsection_detail"),
    path("crsections/<str:section>/", crsection_detail, name="crsection_detail"),
    path("secretadminlogin/", secret_login, name="secret_login"),
    path("api/save-annotation/", save_annotation, name="save_annotation"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
