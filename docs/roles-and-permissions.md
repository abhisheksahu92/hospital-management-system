# Roles and Permissions

Roles are Django Groups populated by `python manage.py bootstrap_hospital`.
`core/roles.py` is the source of truth for model permissions; rerunning the
command resets those four groups to the defined permissions. Permission checks
are server-side. A future view must use Django permission checks for its action
and scope its queryset to records the user may access; hiding navigation is not
authorization.

| Role | Allowed baseline | Explicitly not granted |
|---|---|---|
| Reception | Patient and appointment create/view/change; invoice/payment creation and view; reference data needed to schedule and bill | Clinical notes, diagnoses, prescriptions, pharmacy stock, discounts, refunds, invoice voids, financial adjustments |
| Pharmacy | Minimum patient/prescription lookup permissions; medicine, supplier, receipt, batch, stock-movement, dispensing, OTC sale, return request, stock adjustment and quarantine operations | Appointments, clinical notes/diagnoses writes, patient edits, invoice/payment writes, financial adjustment/refund/void |
| Doctor | Assigned-patient and own-schedule reads, appointment lifecycle updates, consultation and prescription create/view/change, medicine/reference reads | Other doctors' patient records, reception billing, refunds, invoice voids/adjustments, pharmacy stock/sales |
| Administrator | Staff accounts/profiles, role assignment, hospital and operational master data, invoice reads/creation, discounts, refunds, invoice voids, and financial adjustments with reason/audit | Patient-directory, appointment, and clinical-record access; ordinary payment collection |

Sensitive financial operations have explicit Django permissions including
`core.void_invoice`, `core.add_refund`, and `core.add_adjustment`. Administrator
is the sole role granted those actions. No second approver is required in the
single-hospital MVP; each action requires a reason and creates an audit event.
Stock adjustment uses `core.adjust_stock`, granted only to Pharmacy, and records
both a balanced stock movement and an audit event.

## Object Scope

Doctor patient reads must use `core.authorization.doctor_patient_queryset(user)`.
It returns patients linked through that doctor's appointments or consultations;
users without the Doctor group receive an empty queryset. The explicit
`core.view_all_patient_records` permission can broaden access only for a Doctor
role and must be granted deliberately.

The administrator group is not a Django superuser and receives no clinical
permissions. The staff UserAdmin lets administrators assign groups to other
accounts, hides superuser/direct-permission controls, prevents self-changing
group membership, excludes superuser accounts from their list, and disables
account deletion. Only the initial trusted operator should use a superuser
account created through `createsuperuser`.

## Current Boundary

Patient, appointment, clinical, billing, stock, sale, dispense, and return routes
apply server-side checks and object scopes. The pharmacy prescription pages
expose only patient identity, safety notes, and issued prescription items.
Django Admin logs staff/group and OTC-approval changes, while sensitive clinical
read/create/print and financial/stock mutation actions produce AuditEvents.
Full audit review remains under KAN-16.