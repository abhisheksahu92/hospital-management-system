# Roles and Permissions

Roles are Django Groups populated by `python manage.py bootstrap_hospital`.
`core/roles.py` is the source of truth for model permissions; rerunning the
command resets those four groups to the defined permissions. Permission checks
are server-side. A future view must use Django permission checks for its action
and scope its queryset to records the user may access; hiding navigation is not
authorization.

| Role | Allowed baseline | Explicitly not granted |
|---|---|---|
| Reception | Patient and appointment create/view/change; invoice/payment creation and view; reference data needed to schedule and bill | Clinical notes, diagnoses, prescriptions, pharmacy stock, refunds, invoice voids, adjustments |
| Pharmacy | Minimum patient/prescription lookup permissions; medicine, supplier, receipt, batch, stock-movement, dispensing, sale, and return operations | Appointments, clinical notes/diagnoses writes, patient edits, invoice/payment writes, refund approval |
| Doctor | Patient/appointment read, appointment updates, consultation and prescription create/view/change, medicine/reference reads | Payments, refunds, invoice voids/adjustments, pharmacy stock/sales |
| Administrator | Staff accounts/profiles, role assignment, hospital and operational master data | Patient/clinical access and financial write/approval permissions by default |

Sensitive operations have explicit Django permissions: `core.void_invoice`,
`core.approve_refund`, and `core.approve_adjustment`. None of the four baseline
groups receives them. Their assignment requires an approved financial policy
and must be paired with server-side approval workflow controls.

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

The patient, appointment, clinical, billing, and pharmacy workflow views have
not all been implemented yet. These groups define the server-side permission
contract for those tickets; KAN-9 through KAN-14 must apply the checks to every
read/write endpoint and test field-level minimum visibility. Django Admin logs
staff/group changes; sensitive clinical access and operational/financial audit
events are completed under KAN-16.