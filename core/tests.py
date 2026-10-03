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
    Department,
    HospitalSettings,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Patient,
    Service,
    StaffProfile,
    StockMovement,
    StockReceipt,
    Supplier,
    VisitType,
)
from .authorization import doctor_patient_queryset
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
