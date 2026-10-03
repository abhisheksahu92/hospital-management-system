from decimal import Decimal
import re

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import (
    Appointment,
    AuditEvent,
    Consultation,
    Department,
    HospitalSettings,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Patient,
    Prescription,
    Service,
    StaffProfile,
    StockMovement,
    StockReceipt,
    Supplier,
    VisitType,
)
from .authorization import doctor_patient_queryset
from .forms import AppointmentForm, PatientForm
from .services.numbering import next_number


class PublicPagesTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hospital Management System")

    def test_home_page_uses_configured_hospital_name(self):
        HospitalSettings.objects.create(name="Synthetic Community Hospital")

        response = self.client.get("/")

        self.assertContains(response, "Synthetic Community Hospital")

    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class AuthenticationLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff-test",
            email="staff@example.test",
            password="Synthetic-Password-123!",
        )

    def test_active_staff_can_log_in_and_log_out(self):
        response = self.client.post(
            reverse("login"),
            {"username": "staff-test", "password": "Synthetic-Password-123!"},
        )

        self.assertRedirects(response, "/")
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_invalid_and_inactive_users_cannot_log_in(self):
        invalid_response = self.client.post(
            reverse("login"), {"username": "staff-test", "password": "wrong"}
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Please enter a correct")

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive_response = self.client.post(
            reverse("login"),
            {"username": "staff-test", "password": "Synthetic-Password-123!"},
        )
        self.assertEqual(inactive_response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deactivated_user_session_loses_protected_access(self):
        self.client.force_login(self.user)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_password_change_requires_login_and_updates_password(self):
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "Synthetic-Password-123!",
                "new_password1": "New-Synthetic-Password-456!",
                "new_password2": "New-Synthetic-Password-456!",
            },
        )

        self.assertRedirects(response, reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-Synthetic-Password-456!"))

    def test_password_reset_sends_email_without_exposing_user_existence(self):
        response = self.client.post(
            reverse("password_reset"), {"email": self.user.email}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

        reset_path = re.search(
            r"http://testserver(/accounts/reset/[^\s]+)", mail.outbox[0].body
        ).group(1)
        response = self.client.get(reset_path, follow=True)
        self.assertEqual(response.status_code, 200)
        confirm_path = response.request["PATH_INFO"]
        response = self.client.post(
            confirm_path,
            {
                "new_password1": "Reset-Synthetic-Password-789!",
                "new_password2": "Reset-Synthetic-Password-789!",
            },
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Reset-Synthetic-Password-789!"))

        response = self.client.post(
            reverse("password_reset"), {"email": "unknown@example.test"}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_staff_cannot_self_register_or_open_admin(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get("/accounts/signup/").status_code, 404)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_bootstrapped_superuser_can_manage_staff_profiles(self):
        administrator = get_user_model().objects.create_superuser(
            username="admin-test",
            email="admin@example.test",
            password="Synthetic-Admin-Password-123!",
        )
        self.client.force_login(administrator)

        response = self.client.get(reverse("admin:core_staffprofile_changelist"))

        self.assertEqual(response.status_code, 200)


class SchemaConstraintTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            mrn="TEST-001", full_name="Synthetic Patient"
        )

    def test_patient_mrn_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.create(mrn="TEST-001", full_name="Duplicate")

    def test_hospital_settings_has_a_singleton_key(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            HospitalSettings.objects.create(id=2, name="Second Hospital")

    def test_invoice_line_rejects_negative_money(self):
        invoice = Invoice.objects.create(number="INV-TEST-001", patient=self.patient)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InvoiceLine.objects.create(
                invoice=invoice,
                description="Invalid synthetic line",
                quantity=Decimal("1"),
                unit_price=Decimal("-1.00"),
                line_total=Decimal("-1.00"),
            )

    def test_invoice_rejects_unknown_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invoice.objects.create(
                number="INV-TEST-INVALID",
                patient=self.patient,
                status="unknown",
            )

    def test_batch_rejects_negative_stock(self):
        supplier = Supplier.objects.create(code="SUP-TEST", name="Synthetic Supplier")
        receipt = StockReceipt.objects.create(
            number="REC-TEST-001",
            supplier=supplier,
            received_at="2026-01-01T00:00:00Z",
        )
        medicine = Medicine.objects.create(
            code="MED-TEST", generic_name="Synthetic Medicine", unit="tablet"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicineBatch.objects.create(
                medicine=medicine,
                receipt=receipt,
                batch_number="BATCH-TEST",
                expiry_date="2027-01-01",
                purchase_price=Decimal("1.00"),
                sale_price=Decimal("2.00"),
                quantity_received=Decimal("10"),
                quantity_on_hand=Decimal("-1"),
            )

    def test_stock_movement_must_balance(self):
        supplier = Supplier.objects.create(code="SUP-TEST", name="Synthetic Supplier")
        receipt = StockReceipt.objects.create(
            number="REC-TEST-001",
            supplier=supplier,
            received_at="2026-01-01T00:00:00Z",
        )
        medicine = Medicine.objects.create(
            code="MED-TEST", generic_name="Synthetic Medicine", unit="tablet"
        )
        batch = MedicineBatch.objects.create(
            medicine=medicine,
            receipt=receipt,
            batch_number="BATCH-TEST",
            expiry_date="2027-01-01",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("10"),
            quantity_on_hand=Decimal("10"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(
                batch=batch,
                kind=StockMovement.Kind.DISPENSE,
                quantity_delta=Decimal("-2"),
                quantity_before=Decimal("10"),
                quantity_after=Decimal("9"),
            )


class HospitalBootstrapTests(TestCase):
    def test_bootstrap_is_idempotent_and_creates_roles_and_sequences(self):
        call_command("bootstrap_hospital", stdout=None)
        call_command("bootstrap_hospital", stdout=None)

        self.assertEqual(HospitalSettings.objects.count(), 1)
        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)),
            {"Reception", "Pharmacy", "Doctor", "Administrator"},
        )
        self.assertEqual(NumberSequence.objects.count(), 8)

    def test_numbering_allocates_distinct_values_from_config(self):
        NumberSequence.objects.create(code="PATIENT", prefix="P-")

        self.assertEqual(next_number("PATIENT"), "P-1")
        self.assertEqual(next_number("PATIENT"), "P-2")
        self.assertEqual(NumberSequence.objects.get(code="PATIENT").next_value, 3)

    def test_configuration_admin_requires_model_permission(self):
        staff = get_user_model().objects.create_user(
            username="config-staff",
            password="Synthetic-Password-123!",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("admin:core_service_changelist"))

        self.assertEqual(response.status_code, 403)

    def test_service_price_change_does_not_rewrite_invoice_snapshot(self):
        service = Service.objects.create(
            code="CONSULT",
            name="Consultation",
            current_charge=Decimal("500.00"),
        )
        patient = Patient.objects.create(
            mrn="SNAPSHOT-001", full_name="Synthetic Patient"
        )
        invoice = Invoice.objects.create(number="SNAPSHOT-INV", patient=patient)
        line = InvoiceLine.objects.create(
            invoice=invoice,
            service=service,
            description="Consultation",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            tax_rate=None,
            discount_amount=Decimal("0.00"),
            line_total=Decimal("500.00"),
        )

        service.current_charge = Decimal("700.00")
        service.save(update_fields=("current_charge", "updated_at"))
        line.refresh_from_db()

        self.assertEqual(line.unit_price, Decimal("500.00"))
        self.assertIsNone(line.tax_rate)

    def test_admin_master_data_change_is_logged(self):
        administrator = get_user_model().objects.create_superuser(
            username="master-admin",
            email="master-admin@example.test",
            password="Synthetic-Admin-Password-123!",
        )
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("admin:core_service_add"),
            {
                "code": "SVC-TEST",
                "name": "Synthetic Service",
                "current_charge": "",
                "is_active": "on",
                "_save": "Save",
            },
        )

        service = Service.objects.get(code="SVC-TEST")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LogEntry.objects.filter(
                user=administrator,
                content_type__model="service",
                object_id=str(service.pk),
                action_flag=ADDITION,
            ).exists()
        )


class RolePermissionTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)

    def test_each_role_has_only_its_approved_model_permissions(self):
        matrix = {
            "Reception": (
                {"add_patient", "add_appointment", "add_payment"},
                {"view_consultation", "add_refund", "add_medicine"},
            ),
            "Pharmacy": (
                {"view_prescription", "add_stockreceipt", "add_dispensing"},
                {"add_appointment", "add_consultation", "change_patient"},
            ),
            "Doctor": (
                {"view_patient", "add_consultation", "add_prescription"},
                {"add_payment", "add_medicine", "approve_refund"},
            ),
            "Administrator": (
                {"add_user", "add_service", "change_hospitalsettings"},
                {"view_patient", "view_consultation", "add_payment", "void_invoice"},
            ),
        }

        for role, (allowed, denied) in matrix.items():
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(
                    username=f"{role.lower()}-permission-test",
                    password="Synthetic-Password-123!",
                )
                user.groups.add(Group.objects.get(name=role))
                for codename in allowed:
                    self.assertTrue(
                        user.has_perm(f"core.{codename}")
                        or user.has_perm(f"auth.{codename}")
                    )
                for codename in denied:
                    self.assertFalse(
                        user.has_perm(f"core.{codename}")
                        or user.has_perm(f"auth.{codename}")
                    )

    def test_doctor_patient_access_is_limited_to_assigned_patients(self):
        doctor_user = get_user_model().objects.create_user(
            username="scoped-doctor", password="Synthetic-Password-123!"
        )
        doctor_user.groups.add(Group.objects.get(name="Doctor"))
        department = Department.objects.create(code="DOC", name="Synthetic Department")
        doctor = StaffProfile.objects.create(
            user=doctor_user, employee_id="DOC-001", department=department
        )
        other_user = get_user_model().objects.create_user(username="other-doctor")
        other_doctor = StaffProfile.objects.create(
            user=other_user, employee_id="DOC-002", department=department
        )
        visit_type = VisitType.objects.create(code="VISIT", name="Synthetic Visit")
        assigned = Patient.objects.create(mrn="SCOPE-001", full_name="Assigned Patient")
        unrelated = Patient.objects.create(
            mrn="SCOPE-002", full_name="Unrelated Patient"
        )
        Appointment.objects.create(
            patient=assigned,
            doctor=doctor,
            visit_type=visit_type,
            scheduled_at="2026-12-01T09:00:00Z",
        )
        Appointment.objects.create(
            patient=unrelated,
            doctor=other_doctor,
            visit_type=visit_type,
            scheduled_at="2026-12-01T10:00:00Z",
        )

        self.assertEqual(
            list(doctor_patient_queryset(doctor_user).values_list("pk", flat=True)),
            [assigned.pk],
        )

    def test_administrator_cannot_escalate_self_to_superuser(self):
        administrator = get_user_model().objects.create_user(
            username="role-admin",
            password="Synthetic-Password-123!",
            is_staff=True,
        )
        administrator.groups.add(Group.objects.get(name="Administrator"))
        self.client.force_login(administrator)

        add_url = reverse("admin:auth_user_add")
        response = self.client.get(add_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="is_superuser"')
        self.assertNotContains(response, 'name="user_permissions"')

        response = self.client.post(
            add_url,
            {
                "username": "attempted-superuser",
                "password1": "Synthetic-New-Password-123!",
                "password2": "Synthetic-New-Password-123!",
                "is_superuser": "on",
                "is_staff": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="attempted-superuser")
        self.assertFalse(created.is_superuser)
        self.assertFalse(created.user_permissions.exists())


class PatientWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.reception = get_user_model().objects.create_user(
            username="patient-reception", password="Synthetic-Password-123!"
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(
            user=self.reception, employee_id="PAT-RECEPTION-001"
        )

    def test_reception_can_register_with_generated_identifier(self):
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("patient_create"),
            {
                "full_name": "Synthetic Patient One",
                "date_of_birth": "1990-01-02",
                "phone": "5550100",
                "address": "Synthetic Address",
                "emergency_contact_name": "Synthetic Contact",
                "emergency_contact_phone": "5550101",
                "allergy_safety_notes": "must not be accepted from reception",
            },
        )

        patient = Patient.objects.get(full_name="Synthetic Patient One")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(patient.mrn, "1")
        self.assertEqual(patient.allergy_safety_notes, "")
        event = AuditEvent.objects.get(
            action="patient.created", target_id=str(patient.pk)
        )
        self.assertEqual(event.actor, self.reception.staff_profile)
        self.assertIn("full_name", event.details["changed_fields"])
        self.assertNotIn("Synthetic Patient One", str(event.details))

    def test_exact_name_and_phone_duplicate_warns_but_never_merges(self):
        existing = Patient.objects.create(
            mrn="EXISTING-001", full_name="Synthetic Patient", phone="5550110"
        )
        self.client.force_login(self.reception)
        data = {
            "full_name": "Synthetic Patient",
            "phone": "5550110",
            "address": "",
            "emergency_contact_name": "",
            "emergency_contact_phone": "",
        }

        warning = self.client.post(reverse("patient_create"), data)
        self.assertEqual(warning.status_code, 200)
        self.assertContains(warning, "Possible duplicate patient")
        self.assertEqual(Patient.objects.count(), 1)

        data["confirm_duplicate"] = "yes"
        created = self.client.post(reverse("patient_create"), data)
        self.assertEqual(created.status_code, 302)
        self.assertEqual(Patient.objects.count(), 2)
        existing.refresh_from_db()
        self.assertEqual(existing.mrn, "EXISTING-001")

    def test_search_matches_patient_identifier_name_and_phone(self):
        patient = Patient.objects.create(
            mrn="SEARCH-001", full_name="Synthetic Search Patient", phone="5550123"
        )
        self.client.force_login(self.reception)

        for query in ("SEARCH-001", "Search Patient", "5550123"):
            with self.subTest(query=query):
                response = self.client.get(reverse("patient_list"), {"q": query})
                self.assertContains(response, patient.mrn)

    def test_reception_can_update_demographics_but_not_safety_notes(self):
        patient = Patient.objects.create(
            mrn="EDIT-001",
            full_name="Original Name",
            phone="5550130",
            allergy_safety_notes="Synthetic confidential note",
        )
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("patient_update", args=[patient.pk]),
            {
                "full_name": "Updated Name",
                "phone": "5550131",
                "address": "Updated Synthetic Address",
                "emergency_contact_name": "",
                "emergency_contact_phone": "",
                "allergy_safety_notes": "Unauthorized change",
            },
        )

        patient.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(patient.full_name, "Updated Name")
        self.assertEqual(patient.allergy_safety_notes, "Synthetic confidential note")
        detail = self.client.get(reverse("patient_detail", args=[patient.pk]))
        self.assertNotContains(detail, "Synthetic confidential note")
        event = AuditEvent.objects.get(
            action="patient.demographics_updated", target_id=str(patient.pk)
        )
        self.assertEqual(event.actor, self.reception.staff_profile)
        self.assertIn("full_name", event.details["changed_fields"])
        self.assertNotIn("Updated Name", str(event.details))

    def test_future_date_of_birth_is_rejected(self):
        form = PatientForm(
            data={
                "full_name": "Synthetic Patient",
                "date_of_birth": "2999-01-01",
                "phone": "",
                "address": "",
                "emergency_contact_name": "",
                "emergency_contact_phone": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)

    def test_doctor_can_only_open_assigned_patient_and_cannot_edit(self):
        department = Department.objects.create(code="PAT-DOC", name="Synthetic Dept")
        doctor = get_user_model().objects.create_user(
            username="patient-doctor", password="Synthetic-Password-123!"
        )
        doctor.groups.add(Group.objects.get(name="Doctor"))
        doctor_profile = StaffProfile.objects.create(
            user=doctor, employee_id="PAT-DOC-001", department=department
        )
        other_doctor = get_user_model().objects.create_user(
            username="patient-other-doctor"
        )
        other_profile = StaffProfile.objects.create(
            user=other_doctor, employee_id="PAT-DOC-002", department=department
        )
        visit_type = VisitType.objects.create(code="PAT-VISIT", name="Patient Visit")
        assigned = Patient.objects.create(mrn="ASSIGNED-001", full_name="Assigned")
        unrelated = Patient.objects.create(mrn="UNRELATED-001", full_name="Unrelated")
        Appointment.objects.create(
            patient=assigned,
            doctor=doctor_profile,
            visit_type=visit_type,
            scheduled_at="2026-12-02T09:00:00Z",
        )
        Appointment.objects.create(
            patient=unrelated,
            doctor=other_profile,
            visit_type=visit_type,
            scheduled_at="2026-12-02T10:00:00Z",
        )
        self.client.force_login(doctor)

        self.assertEqual(
            self.client.get(reverse("patient_detail", args=[assigned.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("patient_detail", args=[unrelated.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("patient_update", args=[assigned.pk])).status_code,
            403,
        )

    def test_pharmacy_and_administrator_cannot_open_patient_directory(self):
        for role in ("Pharmacy", "Administrator"):
            user = get_user_model().objects.create_user(
                username=f"patient-{role.lower()}", password="Synthetic-Password-123!"
            )
            user.groups.add(Group.objects.get(name=role))
            self.client.force_login(user)
            with self.subTest(role=role):
                self.assertEqual(
                    self.client.get(reverse("patient_list")).status_code, 403
                )
                self.assertEqual(
                    self.client.post(reverse("patient_create")).status_code, 403
                )

    def test_patient_data_is_not_permanently_deletable_through_ui(self):
        patient = Patient.objects.create(mrn="KEEP-001", full_name="Keep Record")
        self.client.force_login(self.reception)

        response = self.client.post(f"/patients/{patient.pk}/delete/")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())


class AppointmentWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.reception = get_user_model().objects.create_user(
            username="appointment-reception",
            password="Synthetic-Password-123!",
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(
            user=self.reception, employee_id="APPT-RECEPTION-001"
        )
        self.doctor = get_user_model().objects.create_user(
            username="appointment-doctor", password="Synthetic-Password-123!"
        )
        self.doctor.groups.add(Group.objects.get(name="Doctor"))
        self.doctor_profile = StaffProfile.objects.create(
            user=self.doctor, employee_id="APPT-DOCTOR-001"
        )
        self.other_doctor = get_user_model().objects.create_user(
            username="appointment-other-doctor"
        )
        self.other_profile = StaffProfile.objects.create(
            user=self.other_doctor, employee_id="APPT-DOCTOR-002"
        )
        self.patient = Patient.objects.create(
            mrn="APPT-PATIENT-001", full_name="Synthetic Appointment Patient"
        )
        self.visit_type = VisitType.objects.create(
            code="APPT-VISIT", name="Synthetic Appointment Visit"
        )

    def make_appointment(
        self,
        *,
        doctor=None,
        patient=None,
        hour=9,
        status=Appointment.Status.SCHEDULED,
    ):
        return Appointment.objects.create(
            patient=patient or self.patient,
            doctor=doctor or self.doctor_profile,
            visit_type=self.visit_type,
            scheduled_at=f"2026-12-03T{hour:02}:00:00Z",
            status=status,
        )

    def test_reception_books_appointment_with_server_controlled_status(self):
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_create"),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T14:30",
                "status": "completed",
            },
        )

        appointment = Appointment.objects.get(patient=self.patient)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="appointment.created", target_id=str(appointment.pk)
            ).exists()
        )

    def test_exact_active_doctor_slot_conflict_is_rejected(self):
        self.make_appointment()
        form = AppointmentForm(
            data={
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T14:30",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("scheduled_at", form.errors)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_appointment()

    def test_reception_can_reschedule_and_change_is_audited(self):
        appointment = self.make_appointment()
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_reschedule", args=[appointment.pk]),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T16:30",
            },
        )

        appointment.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.scheduled_at.hour, 11)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="appointment.rescheduled", target_id=str(appointment.pk)
            ).exists()
        )

    def test_reschedule_into_occupied_slot_shows_conflict(self):
        appointment = self.make_appointment()
        other_patient = Patient.objects.create(
            mrn="APPT-CONFLICT-002", full_name="Conflict Synthetic Patient"
        )
        self.make_appointment(patient=other_patient, hour=10)
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_reschedule", args=[appointment.pk]),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T15:30",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has an active appointment")

    def test_doctor_schedule_contains_only_own_appointments(self):
        own = self.make_appointment()
        other_patient = Patient.objects.create(
            mrn="APPT-PATIENT-002", full_name="Other Synthetic Patient"
        )
        other = self.make_appointment(
            doctor=self.other_profile, patient=other_patient, hour=10
        )
        self.client.force_login(self.doctor)

        response = self.client.get(reverse("appointment_list"), {"date": "2026-12-03"})

        self.assertContains(response, own.patient.mrn)
        self.assertNotContains(response, other.patient.mrn)

    def test_check_in_start_complete_and_audit(self):
        appointment = self.make_appointment()
        self.client.force_login(self.reception)
        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "check_in"},
        )
        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CHECKED_IN)
        self.assertIsNotNone(appointment.checked_in_at)

        self.client.force_login(self.doctor)
        self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "start"},
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.IN_PROGRESS)
        self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "complete"},
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)
        self.assertIsNotNone(appointment.completed_at)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="appointment.status_changed", target_id=str(appointment.pk)
            ).count(),
            3,
        )

    def test_reception_can_mark_no_show_and_timestamp_it(self):
        appointment = self.make_appointment()
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "no_show"},
        )

        appointment.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.status, Appointment.Status.NO_SHOW)
        self.assertIsNotNone(appointment.no_show_at)

    def test_invalid_transition_and_cross_doctor_post_are_rejected(self):
        appointment = self.make_appointment(doctor=self.other_profile)
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "start"},
        )
        self.assertEqual(response.status_code, 404)

        appointment.doctor = self.doctor_profile
        appointment.save(update_fields=("doctor", "updated_at"))
        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "complete"},
        )
        self.assertEqual(response.status_code, 400)

    def test_queue_is_ordered_by_check_in_time(self):
        first = self.make_appointment(hour=10, status=Appointment.Status.CHECKED_IN)
        second_patient = Patient.objects.create(
            mrn="APPT-QUEUE-002", full_name="Second Queue Patient"
        )
        second = self.make_appointment(
            patient=second_patient, hour=11, status=Appointment.Status.CHECKED_IN
        )
        Appointment.objects.filter(pk=first.pk).update(
            checked_in_at="2026-12-03T09:20:00Z"
        )
        Appointment.objects.filter(pk=second.pk).update(
            checked_in_at="2026-12-03T09:10:00Z"
        )
        self.client.force_login(self.reception)

        response = self.client.get(reverse("appointment_list"), {"date": "2026-12-03"})

        queue_html = response.content.decode().split("<h2>Waiting queue</h2>", 1)[1]
        self.assertLess(
            queue_html.index(second.patient.mrn), queue_html.index(first.patient.mrn)
        )

    def test_pharmacy_cannot_view_or_change_appointments(self):
        pharmacy = get_user_model().objects.create_user(username="appointment-pharmacy")
        pharmacy.groups.add(Group.objects.get(name="Pharmacy"))
        appointment = self.make_appointment()
        self.client.force_login(pharmacy)

        self.assertEqual(self.client.get(reverse("appointment_list")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("appointment_transition", args=[appointment.pk]),
                {"action": "cancel"},
            ).status_code,
            403,
        )


class ClinicalWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.doctor = get_user_model().objects.create_user(
            username="clinical-doctor", password="Synthetic-Password-123!"
        )
        self.doctor.groups.add(Group.objects.get(name="Doctor"))
        self.doctor_profile = StaffProfile.objects.create(
            user=self.doctor, employee_id="CLINICAL-DOC-001"
        )
        self.other_doctor = get_user_model().objects.create_user(
            username="clinical-other-doctor"
        )
        self.other_profile = StaffProfile.objects.create(
            user=self.other_doctor, employee_id="CLINICAL-DOC-002"
        )
        self.reception = get_user_model().objects.create_user(
            username="clinical-reception"
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        self.pharmacy = get_user_model().objects.create_user(
            username="clinical-pharmacy"
        )
        self.pharmacy.groups.add(Group.objects.get(name="Pharmacy"))
        self.patient = Patient.objects.create(
            mrn="CLINICAL-PATIENT-001",
            full_name="Synthetic Clinical Patient",
            allergy_safety_notes="Synthetic allergy warning",
        )
        visit_type = VisitType.objects.create(
            code="CLINICAL-VISIT", name="Clinical Visit"
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_profile,
            visit_type=visit_type,
            scheduled_at="2026-12-04T09:00:00Z",
            status=Appointment.Status.IN_PROGRESS,
        )
        self.medicine = Medicine.objects.create(
            code="CLINICAL-MED-001",
            generic_name="Synthetic Medicine",
            strength="10 mg",
            unit="tablet",
        )

    def prescription_post_data(self, **overrides):
        data = {
            "clinical_notes": "Synthetic consultation notes",
            "diagnosis": "Synthetic diagnosis",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine": str(self.medicine.pk),
            "items-0-dosage": "1 tablet",
            "items-0-frequency": "twice daily",
            "items-0-duration": "5 days",
            "items-0-instructions": "Synthetic instructions",
            "items-0-quantity": "10",
        }
        data.update(overrides)
        return data

    def test_doctor_creates_consultation_and_issued_prescription(self):
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse("consultation_create", args=[self.appointment.pk]),
            self.prescription_post_data(),
        )

        consultation = Consultation.objects.get(appointment=self.appointment)
        prescription = Prescription.objects.get(consultation=consultation)
        item = prescription.items.get()
        self.assertRedirects(
            response, reverse("consultation_detail", args=[consultation.pk])
        )
        self.assertEqual(consultation.doctor, self.doctor_profile)
        self.assertEqual(consultation.patient, self.patient)
        self.assertEqual(prescription.number, "1")
        self.assertEqual(prescription.status, Prescription.Status.ISSUED)
        self.assertEqual(item.quantity, Decimal("10"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.consultation_created",
                target_id=str(consultation.pk),
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.prescription_issued",
                target_id=str(prescription.pk),
            ).exists()
        )

    def test_duplicate_submission_reuses_existing_encounter(self):
        self.client.force_login(self.doctor)
        url = reverse("consultation_create", args=[self.appointment.pk])
        self.client.post(url, self.prescription_post_data())

        response = self.client.post(
            url,
            self.prescription_post_data(
                clinical_notes="Duplicate synthetic note",
                diagnosis="Duplicate synthetic diagnosis",
            ),
        )

        self.assertEqual(
            Consultation.objects.filter(appointment=self.appointment).count(), 1
        )
        self.assertRedirects(
            response,
            reverse(
                "consultation_detail",
                args=[Consultation.objects.get(appointment=self.appointment).pk],
            ),
        )

    def test_doctor_cannot_open_another_doctors_appointment(self):
        other_appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.other_profile,
            visit_type=self.appointment.visit_type,
            scheduled_at="2026-12-04T10:00:00Z",
            status=Appointment.Status.IN_PROGRESS,
        )
        self.client.force_login(self.doctor)

        response = self.client.get(
            reverse("consultation_create", args=[other_appointment.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_clinical_history_shows_only_notes_authored_by_current_doctor(self):
        own = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor_profile,
            clinical_notes="Own synthetic clinical note",
            diagnosis="Own synthetic diagnosis",
        )
        Consultation.objects.create(
            patient=self.patient,
            doctor=self.other_profile,
            clinical_notes="Other doctor confidential note",
            diagnosis="Other doctor diagnosis",
        )
        self.client.force_login(self.doctor)

        response = self.client.get(reverse("clinical_history", args=[self.patient.pk]))

        self.assertContains(response, "Own synthetic diagnosis")
        self.assertNotContains(response, "Other doctor diagnosis")
        detail = self.client.get(reverse("consultation_detail", args=[own.pk]))
        self.assertContains(detail, "Own synthetic clinical note")
        self.assertNotContains(detail, "Other doctor confidential note")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.history_viewed", target_id=str(self.patient.pk)
            ).exists()
        )

    def test_empty_consultation_is_rejected(self):
        self.client.force_login(self.doctor)
        response = self.client.post(
            reverse("consultation_create", args=[self.appointment.pk]),
            {
                "clinical_notes": "",
                "diagnosis": "",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consultation.objects.count(), 0)

    def test_reception_and_pharmacy_cannot_read_or_write_clinical_records(self):
        for user in (self.reception, self.pharmacy):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.client.get(
                        reverse("consultation_create", args=[self.appointment.pk])
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.get(
                        reverse("clinical_history", args=[self.patient.pk])
                    ).status_code,
                    403,
                )

    def test_pharmacy_sees_only_prescription_and_safety_data(self):
        consultation = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor_profile,
            clinical_notes="Confidential synthetic clinical note",
            diagnosis="Confidential synthetic diagnosis",
        )
        prescription = Prescription.objects.create(
            number="CLINICAL-RX-001",
            consultation=consultation,
            patient=self.patient,
            doctor=self.doctor_profile,
            status=Prescription.Status.ISSUED,
        )
        prescription.items.create(
            medicine=self.medicine,
            dosage="1 tablet",
            frequency="daily",
            duration="5 days",
            instructions="Synthetic instructions",
            quantity=Decimal("5"),
        )
        self.client.force_login(self.pharmacy)

        queue = self.client.get(reverse("pharmacy_prescription_list"))
        printed = self.client.get(reverse("prescription_print", args=[prescription.pk]))

        for response in (queue, printed):
            self.assertContains(response, "Synthetic allergy warning")
            self.assertContains(response, "Synthetic Medicine")
            self.assertNotContains(response, "Confidential synthetic clinical note")
            self.assertNotContains(response, "Confidential synthetic diagnosis")

        self.assertEqual(
            self.client.get(
                reverse("consultation_detail", args=[consultation.pk])
            ).status_code,
            403,
        )

    def test_pharmacy_cannot_print_unissued_prescription(self):
        prescription = Prescription.objects.create(
            number="CLINICAL-DRAFT-001",
            patient=self.patient,
            doctor=self.doctor_profile,
            status=Prescription.Status.DRAFT,
        )
        self.client.force_login(self.pharmacy)

        response = self.client.get(
            reverse("prescription_print", args=[prescription.pk])
        )

        self.assertEqual(response.status_code, 404)
