from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.models import HospitalSettings, NumberSequence


class Command(BaseCommand):
    help = "Create the initial hospital settings, role groups, and document sequences."

    def handle(self, *args, **options):
        HospitalSettings.objects.get_or_create(
            pk=1,
            defaults={
                "name": "Hospital name not configured",
                "timezone": "Asia/Kolkata",
                "currency_code": "INR",
            },
        )

        for name in ("Reception", "Pharmacy", "Doctor", "Administrator"):
            Group.objects.get_or_create(name=name)

        for code in (
            "PATIENT",
            "INVOICE",
            "RECEIPT",
            "PRESCRIPTION",
            "PHARMACY_SALE",
            "STOCK_RECEIPT",
            "DISPENSING",
            "PHARMACY_RETURN",
        ):
            NumberSequence.objects.get_or_create(code=code)

        self.stdout.write(
            self.style.SUCCESS(
                "Hospital setup created. Set the hospital name and review role permissions."
            )
        )
