# Open Decisions

All entries below are owner/product decisions, not implemented policy. Resolve
them with the hospital's authorized clinical/operations/finance/security owners
before dependent behavior is built. Do not use real patient data in examples,
tests, or development.

## Patient data and record lifecycle

- Approve required patient fields, including date of birth versus age, sex/gender
	where necessary, emergency contact, and whether blood group has a justified
	use. Approve allergy/safety fields and who may see each one.
- Approve patient ID/MRN format and sequence behavior.
- Approve duplicate matching signals, staff review steps, correction and merge
	permissions, archival behavior, and whether any patient data may be permanently
	deleted.

KAN-9 uses a provisional duplicate warning for exact case-insensitive full name
and exact non-empty phone matches. It does not auto-merge or block registration;
Reception must review candidates and can explicitly continue as a separate
record. This heuristic and the patient-field set require owner confirmation.

## Appointment and queue policy

KAN-10 decisions: appointments use 30-minute slots; active appointments for the
same doctor may not overlap; the MVP does not overbook. The waiting queue is FIFO
by actual check-in timestamp, with no clinical-priority queue. Existing role
boundaries and lifecycle transitions remain enforced in the application.

## Clinical and prescription policy

KAN-11 decisions: no structured investigation-order system is in the MVP;
follow-up is a simple date and note. Doctors do not receive unrestricted
cross-doctor clinical history. Pharmacy sees only the prescription and safety
information required for dispensing, never consultation notes or diagnosis.
Diagnosis remains text, and prescriptions retain the approved medicine, dose,
frequency, duration, instruction, and quantity fields.

## Billing and payment policy

KAN-12 decisions: Invoice/Payment is the single financial ledger for hospital
and pharmacy settlement. Pharmacy sale records retain operational details and
link to this ledger. Reception may create invoices and record ordinary payments;
only Administrators may discount, refund, void, or adjust, with a reason and an
audit event. No second approver is required for the single-hospital MVP. Tax is
zero until the hospital enters its actual policy. Issued invoices and payments
are immutable; corrections are explicit adjustment/refund transactions. A
payment cannot exceed the current invoice balance.

## Pharmacy and stock policy

KAN-13/KAN-14 decisions: batch and expiry are authoritative; expired or
quarantined stock cannot normally be sold or dispensed. FEFO is the default
selection suggestion. Stock adjustments require permission and a reason. OTC
sales are limited to explicitly approved medicines. Returns reference their
originating transaction. Pharmacy sales and prescription dispensing use the
shared Invoice/Payment ledger; pharmacy operations do not create a separate cash
ledger.

## Reports, privacy, and operations

- Approve each report's purpose, metrics/calculation, date boundaries, filters,
	and role-based export permissions.
- Approve data retention/deletion periods, audit scope, consent/notice needs,
	sensitive-record access review, and data-subject correction handling.
- Approve hosting provider and data region, backup/restore objectives, recovery
	testing, monitoring, and incident/rollback procedures before staging/go-live.

## Platform role

Django remains the application and authentication authority. Supabase is
approved for PostgreSQL and private Storage only; do not use Supabase Auth.
Render is the Django staging host, Cloudflare provides DNS/HTTPS/proxy, Sentry
provides error monitoring, and UptimeRobot or equivalent provides uptime
monitoring. No Supabase client/storage integration is configured in this repo;
do not connect or migrate data until the KAN-24 deployment work is approved.

## KAN-20 bootstrap boundary

The reproducible `bootstrap_hospital` command creates the singleton settings row
with a placeholder name, four Django role groups with code-defined permissions,
and named sequence rows. It does not create a default administrator. The operator
must run `createsuperuser`, replace the hospital placeholder, and review group
permissions before onboarding staff. Rerunning the command reapplies each
role's permission set from `core/roles.py`. Unapproved finance/tax rules and
number formatting remain unset.