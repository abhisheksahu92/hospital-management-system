from django.contrib import admin

from .models import StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "user", "department", "job_title")
    list_filter = ("department",)
    search_fields = ("employee_id", "user__username", "user__email")
