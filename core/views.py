from django.http import JsonResponse
from django.shortcuts import render

from .models import HospitalSettings


def home(request):
    hospital = HospitalSettings.objects.filter(pk=1).only("name").first()
    return render(request, "core/home.html", {"hospital": hospital})


def health(request):
    return JsonResponse({"status": "ok"})
