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
    path("appointments/", views.appointment_list, name="appointment_list"),
    path("appointments/create/", views.appointment_create, name="appointment_create"),
    path(
        "appointments/<int:pk>/reschedule/",
        views.appointment_reschedule,
        name="appointment_reschedule",
    ),
    path(
        "appointments/<int:pk>/transition/",
        views.appointment_transition,
        name="appointment_transition",
    ),
    path(
        "clinical/patients/<int:patient_id>/",
        views.clinical_history,
        name="clinical_history",
    ),
    path(
        "consultations/appointment/<int:appointment_id>/",
        views.consultation_create,
        name="consultation_create",
    ),
    path(
        "consultations/<int:pk>/",
        views.consultation_detail,
        name="consultation_detail",
    ),
    path(
        "prescriptions/<int:pk>/print/",
        views.prescription_print,
        name="prescription_print",
    ),
    path(
        "pharmacy/prescriptions/",
        views.pharmacy_prescription_list,
        name="pharmacy_prescription_list",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]
