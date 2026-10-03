from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .authorization import doctor_patient_queryset
from .forms import PatientForm
from .models import AuditEvent, HospitalSettings, Patient, StaffProfile
from .services.numbering import next_number


def home(request):
    hospital = HospitalSettings.objects.filter(pk=1).only("name").first()
    return render(request, "core/home.html", {"hospital": hospital})


def health(request):
    return JsonResponse({"status": "ok"})


def _has_role(user, role):
    return user.groups.filter(name=role).exists()


def _patient_read_queryset(user):
    if _has_role(user, "Reception") and StaffProfile.objects.filter(user=user).exists():
        return Patient.objects.filter(archived_at__isnull=True)
    if _has_role(user, "Doctor"):
        return doctor_patient_queryset(user).filter(archived_at__isnull=True)
    raise PermissionDenied


def _audit_patient_change(request, patient, action, changed_fields):
    actor = StaffProfile.objects.filter(user=request.user).first()
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type="patient",
        target_id=str(patient.pk),
        details={"changed_fields": sorted(changed_fields)},
    )


@permission_required("core.view_patient", raise_exception=True)
def patient_list(request):
    patients = _patient_read_queryset(request.user)
    query = request.GET.get("q", "").strip()
    if query:
        patients = patients.filter(
            Q(mrn__icontains=query)
            | Q(full_name__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(
        request,
        "core/patients/list.html",
        {
            "patients": patients.order_by("full_name", "mrn"),
            "query": query,
            "can_register": _has_role(request.user, "Reception"),
        },
    )


@permission_required("core.add_patient", raise_exception=True)
def patient_create(request):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied

    form = PatientForm(request.POST or None)
    duplicates = Patient.objects.none()
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
        if phone:
            duplicates = Patient.objects.filter(
                archived_at__isnull=True,
                full_name__iexact=form.cleaned_data["full_name"],
                phone__iexact=phone,
            ).order_by("full_name", "mrn")

        if not duplicates.exists() or request.POST.get("confirm_duplicate") == "yes":
            with transaction.atomic():
                patient = form.save(commit=False)
                patient.mrn = next_number("PATIENT")
                patient.save()
                _audit_patient_change(
                    request, patient, "patient.created", form.changed_data
                )
            return redirect("patient_detail", pk=patient.pk)

    return render(
        request,
        "core/patients/form.html",
        {"form": form, "duplicates": duplicates, "creating": True},
    )


@permission_required("core.view_patient", raise_exception=True)
def patient_detail(request, pk):
    patient = get_object_or_404(_patient_read_queryset(request.user), pk=pk)
    return render(
        request,
        "core/patients/detail.html",
        {"patient": patient, "can_edit": _has_role(request.user, "Reception")},
    )


@permission_required("core.change_patient", raise_exception=True)
def patient_update(request, pk):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    patient = get_object_or_404(Patient.objects.filter(archived_at__isnull=True), pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        changed_fields = form.changed_data
        if changed_fields:
            with transaction.atomic():
                patient = form.save()
                _audit_patient_change(
                    request, patient, "patient.demographics_updated", changed_fields
                )
        return redirect("patient_detail", pk=patient.pk)

    return render(
        request,
        "core/patients/form.html",
        {"form": form, "creating": False, "patient": patient},
    )
