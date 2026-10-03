from django.contrib import admin

from .models import (
    Department,
    HospitalSettings,
    Medicine,
    NumberSequence,
    PaymentMethod,
    Service,
    StaffProfile,
    Supplier,
    VisitType,
)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "user", "department", "job_title")
    list_filter = ("department",)
    search_fields = ("employee_id", "user__username", "user__email")


@admin.register(HospitalSettings)
class HospitalSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not HospitalSettings.objects.exists() and super().has_add_permission(
            request
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("code", "prefix", "next_value", "updated_at")
    search_fields = ("code", "prefix")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(VisitType)
class VisitTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "current_charge", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "phone", "email", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "phone", "email")


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("code", "generic_name", "brand_name", "unit", "is_active")
    list_filter = ("is_active", "dosage_form")
    search_fields = ("code", "generic_name", "brand_name", "barcode")
