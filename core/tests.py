from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

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
