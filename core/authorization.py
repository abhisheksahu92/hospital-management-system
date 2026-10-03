from django.db.models import Q

from core.models import Patient, StaffProfile


def doctor_patient_queryset(user):
    if not user.is_authenticated or not user.groups.filter(name="Doctor").exists():
        return Patient.objects.none()

    if user.has_perm("core.view_all_patient_records"):
        return Patient.objects.all()

    profile = StaffProfile.objects.filter(user=user).first()
    if profile is None:
        return Patient.objects.none()

    return Patient.objects.filter(
        Q(appointments__doctor=profile) | Q(consultations__doctor=profile)
    ).distinct()
