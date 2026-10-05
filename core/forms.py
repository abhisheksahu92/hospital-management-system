from django import forms
from datetime import timedelta
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    Appointment,
    Consultation,
    Patient,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    VisitType,
)

APPOINTMENT_DURATION = timedelta(minutes=30)


def appointment_slot_conflicts(doctor, scheduled_at, exclude_pk=None):
    conflicts = Appointment.objects.filter(
        doctor=doctor,
        scheduled_at__gt=scheduled_at - APPOINTMENT_DURATION,
        scheduled_at__lt=scheduled_at + APPOINTMENT_DURATION,
        status__in=(
            Appointment.Status.SCHEDULED,
            Appointment.Status.CHECKED_IN,
            Appointment.Status.IN_PROGRESS,
        ),
    )
    if exclude_pk:
        conflicts = conflicts.exclude(pk=exclude_pk)
    return conflicts.exists()


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = (
            "full_name",
            "date_of_birth",
            "phone",
            "email",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
        )
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "email": forms.EmailInput(attrs={"placeholder": "patient@example.com"}),
        }

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("date_of_birth")
        if date_of_birth and date_of_birth > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return date_of_birth


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ("patient", "doctor", "visit_type", "scheduled_at")
        widgets = {
            "scheduled_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(
            archived_at__isnull=True
        )
        self.fields["doctor"].queryset = (
            StaffProfile.objects.filter(
                user__groups__name="Doctor", user__is_active=True
            )
            .select_related("user")
            .distinct()
        )
        self.fields["visit_type"].queryset = VisitType.objects.filter(is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        scheduled_at = cleaned_data.get("scheduled_at")
        if doctor and scheduled_at:
            if appointment_slot_conflicts(doctor, scheduled_at, self.instance.pk):
                self.add_error(
                    "scheduled_at",
                    "This doctor already has an overlapping active appointment.",
                )
        return cleaned_data


class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = ("clinical_notes", "diagnosis", "follow_up_date", "follow_up_note")
        widgets = {
            "clinical_notes": forms.Textarea(attrs={"rows": 6}),
            "diagnosis": forms.Textarea(attrs={"rows": 3}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "follow_up_note": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("clinical_notes") and not cleaned_data.get("diagnosis"):
            raise forms.ValidationError("Enter clinical notes or a diagnosis.")
        return cleaned_data


class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = (
            "medicine",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "quantity",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medicine"].queryset = self.fields["medicine"].queryset.filter(
            is_active=True
        )


PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=1,
    can_delete=False,
)
