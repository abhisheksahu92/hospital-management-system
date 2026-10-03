from django.contrib import admin
from django.urls import include, path

from core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("patients/", views.patient_list, name="patient_list"),
    path("patients/register/", views.patient_create, name="patient_create"),
    path("patients/<int:pk>/", views.patient_detail, name="patient_detail"),
    path("patients/<int:pk>/edit/", views.patient_update, name="patient_update"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]
