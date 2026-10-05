import os
from core.models import HospitalSettings

def hospital_context(request):
    hospital = HospitalSettings.objects.filter(pk=1).first()
    return {
        "hospital": hospital,
        "POSTHOG_KEY": os.getenv("POSTHOG_KEY", ""),
        "POSTHOG_HOST": os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com"),
    }
