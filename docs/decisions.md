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

- Approve visit types, appointment statuses, lifecycle transitions, and which
	staff may create or change each state.
- Approve doctor schedules, slot duration/capacity, scheduling horizon, holidays,
	conflict handling, and overbooking behavior.
- Approve reschedule, cancellation, late arrival, no-show, and completion rules.
- Approve queue numbering/reset boundaries, ordering, priority, and manual
	override permissions.

KAN-10 currently rejects an exact doctor/start-time collision, allows
rescheduling only while scheduled, permits Reception to check in/cancel scheduled
or checked-in visits and mark a scheduled visit no-show, and permits the assigned
Doctor to start checked-in and complete in-progress visits. Its provisional
waiting queue sorts by `checked_in_at` then appointment ID and does not assign a
queue number. These choices do not resolve appointment duration/overlap,
overbooking, late-arrival, priority, or queue-number policy; owner confirmation
is still required.

## Clinical and prescription policy

- Approve consultation fields, diagnosis representation, clinical history scope,
	and correction/history rules.
- Approve prescription fields, dose/instruction representation, refill and
	partial-dispense rules, and prescription validity/expiry.
- Approve which investigations and follow-up fields are in the MVP.
- Approve the minimum prescription and safety data pharmacy may view.

KAN-11 currently represents diagnosis as text, supports medicine/dosage/frequency/
duration/instructions/quantity on an issued prescription, and does not model
investigation requests or follow-up plans. Doctors see only their own authored
consultation notes; the pharmacy views issued prescription items and the current
patient safety-notes field, never consultation notes or diagnosis. Clinical
owners must approve these fields and any cross-doctor history access before they
are broadened.

## Billing and payment policy

- Approve service catalogue/charges, invoice and receipt formats, numbering, and
	whether prices are fixed or configurable by visit/service.
- Approve payment methods, partial payments, discounts, tax applicability/rates,
	rounding, and receipt issuance behavior.
- Approve void, refund, adjustment, reversal, refund destination/method,
	approval limits, and separation of duties.
- Decide whether pharmacy sales share the main invoice/payment ledger or use a
	separate pharmacy receipt flow; define reconciliation either way.

## Pharmacy and stock policy

- Approve medicine fields (generic/brand, strength, form, unit, identifiers,
	applicable HSN/tax data, prices, reorder level, and active state) and supplier
	fields.
- Approve receiving references, batch/expiry rules, purchase/sale price history,
	stock adjustment reasons, and who may adjust stock.
- Approve FEFO exceptions, partial dispensing/refills, authorized OTC/counter
	sales, return/correction eligibility, expired stock quarantine/disposal, and
	payment/reconciliation behavior.

## Reports, privacy, and operations

- Approve each report's purpose, metrics/calculation, date boundaries, filters,
	and role-based export permissions.
- Approve data retention/deletion periods, audit scope, consent/notice needs,
	sensitive-record access review, and data-subject correction handling.
- Approve hosting provider and data region, backup/restore objectives, recovery
	testing, monitoring, and incident/rollback procedures before staging/go-live.

## Supabase role

Status: Unresolved; do not connect or migrate data.

The application foundation uses Django with PostgreSQL as its intended
relational database. No Supabase project, client, or data integration is
configured. The product owner must decide whether Supabase has a separate
approved role (authentication, database, storage, or not used in the application
path) and document its data access and security responsibilities before any
hospital data is exposed to it.

## KAN-20 bootstrap boundary

The reproducible `bootstrap_hospital` command creates the singleton settings row
with a placeholder name, four Django role groups with code-defined permissions,
and named sequence rows. It does not create a default administrator. The operator
must run `createsuperuser`, replace the hospital placeholder, and review group
permissions before onboarding staff. Rerunning the command reapplies each
role's permission set from `core/roles.py`. Unapproved finance/tax rules and
number formatting remain unset.