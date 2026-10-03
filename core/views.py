from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import HttpResponseBadRequest, JsonResponse
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .authorization import doctor_patient_queryset
from .forms import AppointmentForm, PatientForm
from .models import Appointment, AuditEvent, HospitalSettings, Patient, StaffProfile
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


def _appointment_read_queryset(user):
    if _has_role(user, "Reception") and StaffProfile.objects.filter(user=user).exists():
        return Appointment.objects.all()
    if _has_role(user, "Doctor"):
        return Appointment.objects.filter(doctor__user=user)
    raise PermissionDenied


def _audit_appointment_change(request, appointment, action, details):
    actor = StaffProfile.objects.filter(user=request.user).first()
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type="appointment",
        target_id=str(appointment.pk),
        details=details,
    )


@permission_required("core.view_appointment", raise_exception=True)
def appointment_list(request):
    raw_day = request.GET.get("date", "")
    selected_day = parse_date(raw_day) if raw_day else timezone.localdate()
    if selected_day is None:
        return HttpResponseBadRequest("Invalid appointment date.")

    appointments = _appointment_read_queryset(request.user).filter(
        scheduled_at__date=selected_day
    )
    queue = appointments.filter(status=Appointment.Status.CHECKED_IN).order_by(
        "checked_in_at", "pk"
    )
    return render(
        request,
        "core/appointments/list.html",
        {
            "appointments": appointments.select_related(
                "patient", "doctor__user", "visit_type"
            ).order_by("scheduled_at", "pk"),
            "queue": queue.select_related("patient", "doctor__user", "visit_type"),
            "selected_day": selected_day,
            "is_reception": _has_role(request.user, "Reception"),
            "is_doctor": _has_role(request.user, "Doctor"),
        },
    )


@permission_required("core.add_appointment", raise_exception=True)
def appointment_create(request):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    form = AppointmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                appointment = form.save()
                _audit_appointment_change(
                    request,
                    appointment,
                    "appointment.created",
                    {"status": appointment.status},
                )
        except IntegrityError:
            form.add_error(
                "scheduled_at",
                "This doctor already has an active appointment at that start time.",
            )
        else:
            return redirect("appointment_list")
    return render(
        request,
        "core/appointments/form.html",
        {"form": form, "creating": True},
    )


@permission_required("core.change_appointment", raise_exception=True)
def appointment_reschedule(request, pk):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    appointment = get_object_or_404(
        Appointment.objects.filter(status=Appointment.Status.SCHEDULED), pk=pk
    )
    form = AppointmentForm(request.POST or None, instance=appointment)
    if request.method == "POST" and form.is_valid():
        changed_fields = form.changed_data
        try:
            with transaction.atomic():
                appointment = form.save()
                _audit_appointment_change(
                    request,
                    appointment,
                    "appointment.rescheduled",
                    {"changed_fields": sorted(changed_fields)},
                )
        except IntegrityError:
            form.add_error(
                "scheduled_at",
                "This doctor already has an active appointment at that start time.",
            )
        else:
            return redirect("appointment_list")
    return render(
        request,
        "core/appointments/form.html",
        {"form": form, "creating": False, "appointment": appointment},
    )


@permission_required("core.change_appointment", raise_exception=True)
def appointment_transition(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Appointment actions require POST.")
    appointments = _appointment_read_queryset(request.user)
    appointment = get_object_or_404(appointments, pk=pk)
    action = request.POST.get("action", "")
    reception_transitions = {
        (Appointment.Status.SCHEDULED, "check_in"): Appointment.Status.CHECKED_IN,
        (Appointment.Status.SCHEDULED, "cancel"): Appointment.Status.CANCELLED,
        (Appointment.Status.SCHEDULED, "no_show"): Appointment.Status.NO_SHOW,
        (Appointment.Status.CHECKED_IN, "cancel"): Appointment.Status.CANCELLED,
    }
    doctor_transitions = {
        (Appointment.Status.CHECKED_IN, "start"): Appointment.Status.IN_PROGRESS,
        (Appointment.Status.IN_PROGRESS, "complete"): Appointment.Status.COMPLETED,
    }
    transitions = (
        reception_transitions
        if _has_role(request.user, "Reception")
        else doctor_transitions
        if _has_role(request.user, "Doctor")
        else {}
    )
    previous_status = appointment.status
    next_status = transitions.get((previous_status, action))
    if next_status is None:
        return HttpResponseBadRequest("Invalid appointment status transition.")

    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
        if appointment.status != previous_status:
            return HttpResponseBadRequest(
                "Appointment status changed; refresh and retry."
            )
        appointment.status = next_status
        timestamp = timezone.now()
        update_fields = ["status", "updated_at"]
        if action == "check_in":
            appointment.checked_in_at = timestamp
            update_fields.append("checked_in_at")
        elif action == "start":
            appointment.started_at = timestamp
            update_fields.append("started_at")
        elif action == "complete":
            appointment.completed_at = timestamp
            update_fields.append("completed_at")
        elif action == "cancel":
            appointment.cancelled_at = timestamp
            update_fields.append("cancelled_at")
        elif action == "no_show":
            appointment.no_show_at = timestamp
            update_fields.append("no_show_at")
        appointment.save(update_fields=update_fields)
        _audit_appointment_change(
            request,
            appointment,
            "appointment.status_changed",
            {"from": previous_status, "to": next_status},
        )
    return redirect("appointment_list")
