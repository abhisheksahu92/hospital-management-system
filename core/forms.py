from django import forms
from django.utils import timezone

from .models import Appointment, Patient, StaffProfile, VisitType


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = (
            "full_name",
            "date_of_birth",
            "phone",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
        )
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

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
            conflicts = Appointment.objects.filter(
                doctor=doctor,
                scheduled_at=scheduled_at,
                status__in=(
                    Appointment.Status.SCHEDULED,
                    Appointment.Status.CHECKED_IN,
                    Appointment.Status.IN_PROGRESS,
                ),
            )
            if self.instance.pk:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            if conflicts.exists():
                self.add_error(
                    "scheduled_at",
                    "This doctor already has an active appointment at that start time.",
                )
        return cleaned_data
