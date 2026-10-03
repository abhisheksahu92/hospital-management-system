from decimal import Decimal
import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import (
    HospitalSettings,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicineBatch,
    Patient,
    StockMovement,
    StockReceipt,
    Supplier,
)


class PublicPagesTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hospital Management System")

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
