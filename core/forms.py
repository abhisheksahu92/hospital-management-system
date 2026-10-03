from django import forms
from django.utils import timezone

from .models import Patient


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
