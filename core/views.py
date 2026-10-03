from decimal import Decimal

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .authorization import doctor_patient_queryset
from .forms import (
    AppointmentForm,
    ConsultationForm,
    PatientForm,
    PrescriptionItemFormSet,
)
from .models import (
    Appointment,
    AuditEvent,
    Consultation,
    Dispensing,
    DispensingLine,
    HospitalSettings,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicineBatch,
    Patient,
    Payment,
    PaymentMethod,
    Prescription,
    PrescriptionItem,
    Service,
    StaffProfile,
    StockMovement,
    StockReceipt,
    Supplier,
)
from .services.numbering import next_number


def _login_throttle_key(request, username):
    return f"login-fail:{request.META.get('REMOTE_ADDR', 'unknown')}:{(username or '').strip().lower()}"


class HospitalLoginView(LoginView):
    def dispatch(self, request, *args, **kwargs):
        username = (request.POST.get("username", "") or "").strip().lower()
        if request.method == "POST" and cache.get(_login_throttle_key(request, username), 0) >= 5:
            response = HttpResponse(
                "Too many failed login attempts. Please wait a few minutes and try again.",
                status=429,
            )
            return response
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        username = (self.request.POST.get("username", "") or "").strip().lower()
        key = _login_throttle_key(self.request, username)
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, timeout=600)
        if attempts >= 5:
            return HttpResponse(
                "Too many failed login attempts. Please wait a few minutes and try again.",
                status=429,
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        username = (self.request.POST.get("username", "") or "").strip().lower()
        cache.delete(_login_throttle_key(self.request, username))
        return super().form_valid(form)


def home(request):
    hospital = HospitalSettings.objects.filter(pk=1).only("name").first()
    return render(
        request,
        "core/home.html",
        {
            "hospital": hospital,
            "is_pharmacy": request.user.is_authenticated
            and _has_role(request.user, "Pharmacy"),
        },
    )


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


@permission_required("core.add_invoice", raise_exception=True)
def invoice_create(request):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied

    patient = get_object_or_404(
        Patient.objects.filter(archived_at__isnull=True),
        pk=request.POST.get("patient"),
    )
    service = get_object_or_404(Service, pk=request.POST.get("service"))
    quantity = Decimal(request.POST.get("quantity", "1"))
    unit_price = Decimal(request.POST.get("unit_price", service.current_charge or 0))
    description = request.POST.get("description", service.name).strip() or service.name
    line_total = quantity * unit_price

    invoice = Invoice.objects.create(
        number=next_number("INVOICE"),
        patient=patient,
        status=Invoice.Status.ISSUED,
        subtotal=line_total,
        total=line_total,
        issued_at=timezone.now(),
        created_by=StaffProfile.objects.get(user=request.user),
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        service=service,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        discount_amount=Decimal("0.00"),
        line_total=line_total,
    )
    return redirect("patient_detail", pk=patient.pk)


@permission_required("core.add_payment", raise_exception=True)
def payment_create(request, pk):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied

    invoice = get_object_or_404(Invoice, pk=pk)
    method = get_object_or_404(PaymentMethod, pk=request.POST.get("method"))
    amount = Decimal(request.POST.get("amount", "0"))
    if amount <= 0:
        raise PermissionDenied

    Payment.objects.create(
        receipt_number=next_number("RECEIPT"),
        invoice=invoice,
        method=method,
        amount=amount,
        reference=request.POST.get("reference", "").strip(),
        received_by=StaffProfile.objects.get(user=request.user),
        received_at=timezone.now(),
    )
    return redirect("patient_detail", pk=invoice.patient_id)


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
        {
            "patient": patient,
            "can_edit": _has_role(request.user, "Reception"),
            "can_view_clinical": _has_role(request.user, "Doctor"),
        },
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


def _doctor_profile(user):
    if not _has_role(user, "Doctor"):
        raise PermissionDenied
    profile = StaffProfile.objects.filter(user=user).first()
    if profile is None:
        raise PermissionDenied
    return profile


def _audit_clinical_access(request, action, target_type, target_id):
    actor = StaffProfile.objects.filter(user=request.user).first()
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details={},
    )


@permission_required("core.view_consultation", raise_exception=True)
def clinical_history(request, patient_id):
    profile = _doctor_profile(request.user)
    patient = get_object_or_404(
        doctor_patient_queryset(request.user).filter(archived_at__isnull=True),
        pk=patient_id,
    )
    consultations = Consultation.objects.filter(
        patient=patient, doctor=profile
    ).order_by("-created_at")
    _audit_clinical_access(request, "clinical.history_viewed", "patient", patient.pk)
    return render(
        request,
        "core/clinical/history.html",
        {"patient": patient, "consultations": consultations},
    )


@permission_required("core.add_consultation", raise_exception=True)
def consultation_create(request, appointment_id):
    profile = _doctor_profile(request.user)
    appointment = get_object_or_404(
        Appointment.objects.filter(
            doctor=profile, status=Appointment.Status.IN_PROGRESS
        ).select_related("patient"),
        pk=appointment_id,
    )
    existing = Consultation.objects.filter(appointment=appointment).first()
    if existing:
        return redirect("consultation_detail", pk=existing.pk)

    form = ConsultationForm(request.POST or None)
    item_formset = PrescriptionItemFormSet(request.POST or None, prefix="items")
    if request.method == "POST" and form.is_valid() and item_formset.is_valid():
        try:
            with transaction.atomic():
                consultation = form.save(commit=False)
                consultation.appointment = appointment
                consultation.patient = appointment.patient
                consultation.doctor = profile
                consultation.save()
                _audit_clinical_access(
                    request,
                    "clinical.consultation_created",
                    "consultation",
                    consultation.pk,
                )

                if any(item_form.has_changed() for item_form in item_formset.forms):
                    prescription = Prescription.objects.create(
                        number=next_number("PRESCRIPTION"),
                        consultation=consultation,
                        patient=appointment.patient,
                        doctor=profile,
                        status=Prescription.Status.ISSUED,
                        issued_at=timezone.now(),
                    )
                    item_formset.instance = prescription
                    item_formset.save()
                    _audit_clinical_access(
                        request,
                        "clinical.prescription_issued",
                        "prescription",
                        prescription.pk,
                    )
        except IntegrityError:
            existing = Consultation.objects.filter(appointment=appointment).first()
            if existing is None:
                raise
            return redirect("consultation_detail", pk=existing.pk)
        return redirect("consultation_detail", pk=consultation.pk)

    return render(
        request,
        "core/clinical/consultation_form.html",
        {
            "appointment": appointment,
            "form": form,
            "item_formset": item_formset,
        },
    )


@permission_required("core.view_consultation", raise_exception=True)
def consultation_detail(request, pk):
    profile = _doctor_profile(request.user)
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient", "doctor__user", "appointment"),
        pk=pk,
        doctor=profile,
    )
    prescriptions = consultation.prescriptions.prefetch_related(
        "items__medicine"
    ).order_by("created_at")
    _audit_clinical_access(
        request, "clinical.consultation_viewed", "consultation", consultation.pk
    )
    return render(
        request,
        "core/clinical/consultation_detail.html",
        {"consultation": consultation, "prescriptions": prescriptions},
    )


@permission_required("core.view_prescription", raise_exception=True)
def prescription_print(request, pk):
    if _has_role(request.user, "Doctor"):
        profile = _doctor_profile(request.user)
        prescriptions = Prescription.objects.filter(doctor=profile)
    elif _has_role(request.user, "Pharmacy"):
        prescriptions = Prescription.objects.filter(status=Prescription.Status.ISSUED)
    else:
        raise PermissionDenied
    prescription = get_object_or_404(
        prescriptions.select_related("patient", "doctor__user", "consultation"),
        pk=pk,
    )
    _audit_clinical_access(
        request, "clinical.prescription_printed", "prescription", prescription.pk
    )
    return render(
        request,
        "core/clinical/prescription_print.html",
        {
            "prescription": prescription,
            "items": prescription.items.select_related("medicine"),
        },
    )


@permission_required("core.add_stockreceipt", raise_exception=True)
def stock_receipt_create(request):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Stock receipts require POST.")

    supplier = get_object_or_404(Supplier, pk=request.POST.get("supplier"))
    medicine = get_object_or_404(Medicine, pk=request.POST.get("medicine"))
    quantity_received = Decimal(request.POST.get("quantity_received", "0"))
    if quantity_received <= 0:
        return HttpResponseBadRequest("Quantity received must be positive.")

    expiry_date = request.POST.get("expiry_date")
    if not expiry_date:
        return HttpResponseBadRequest("Expiry date is required.")

    receipt = StockReceipt.objects.create(
        number=next_number("STOCK_RECEIPT"),
        supplier=supplier,
        received_at=timezone.now(),
        received_by=StaffProfile.objects.get(user=request.user),
    )
    batch = MedicineBatch.objects.create(
        medicine=medicine,
        receipt=receipt,
        batch_number=request.POST.get("batch_number", "").strip() or "BATCH-UNKNOWN",
        expiry_date=expiry_date,
        purchase_price=Decimal(request.POST.get("purchase_price", "0.00")),
        sale_price=Decimal(request.POST.get("sale_price", "0.00")),
        quantity_received=quantity_received,
        quantity_on_hand=quantity_received,
    )
    StockMovement.objects.create(
        batch=batch,
        kind=StockMovement.Kind.RECEIPT,
        quantity_delta=quantity_received,
        quantity_before=Decimal("0"),
        quantity_after=quantity_received,
        reference_type="stock_receipt",
        reference_id=str(receipt.pk),
        actor=StaffProfile.objects.get(user=request.user),
    )
    return redirect("pharmacy_prescription_list")


@permission_required("core.add_dispensing", raise_exception=True)
def dispense_prescription(request, prescription_id):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Dispensing requires POST.")

    prescription = get_object_or_404(
        Prescription.objects.filter(status=Prescription.Status.ISSUED),
        pk=prescription_id,
    )
    item = get_object_or_404(
        PrescriptionItem.objects.filter(prescription=prescription),
        pk=request.POST.get("prescription_item"),
    )
    batch = get_object_or_404(
        MedicineBatch.objects.filter(medicine=item.medicine),
        pk=request.POST.get("batch"),
    )
    quantity = Decimal(request.POST.get("quantity", "0"))
    if quantity <= 0:
        return HttpResponseBadRequest("Dispensed quantity must be positive.")
    if quantity > item.quantity:
        return HttpResponseBadRequest("Dispensed quantity exceeds the prescription amount.")
    if batch.quantity_on_hand < quantity:
        return HttpResponseBadRequest("Insufficient stock available for this batch.")

    dispensing = Dispensing.objects.create(
        number=next_number("DISPENSING"),
        prescription=prescription,
        patient=prescription.patient,
        dispensed_by=StaffProfile.objects.get(user=request.user),
        status=Dispensing.Status.COMPLETED,
        dispensed_at=timezone.now(),
    )
    DispensingLine.objects.create(
        dispensing=dispensing,
        prescription_item=item,
        batch=batch,
        quantity=quantity,
        unit_price=batch.sale_price,
    )
    before = batch.quantity_on_hand
    batch.quantity_on_hand = before - quantity
    batch.save(update_fields=("quantity_on_hand", "updated_at"))
    StockMovement.objects.create(
        batch=batch,
        kind=StockMovement.Kind.DISPENSE,
        quantity_delta=-quantity,
        quantity_before=before,
        quantity_after=before - quantity,
        reference_type="dispensing",
        reference_id=str(dispensing.pk),
        actor=StaffProfile.objects.get(user=request.user),
    )
    return redirect("pharmacy_prescription_list")


@permission_required("core.view_prescription", raise_exception=True)
def pharmacy_prescription_list(request):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    prescriptions = Prescription.objects.filter(status=Prescription.Status.ISSUED)
    if query:
        prescriptions = prescriptions.filter(
            Q(number__icontains=query)
            | Q(patient__mrn__icontains=query)
            | Q(patient__full_name__icontains=query)
        )
    return render(
        request,
        "core/clinical/pharmacy_prescriptions.html",
        {
            "prescriptions": prescriptions.select_related("patient").prefetch_related(
                "items__medicine"
            ),
            "query": query,
        },
    )
