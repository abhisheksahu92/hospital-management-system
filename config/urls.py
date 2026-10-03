from django.contrib import admin
from django.urls import include, path

from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]
