# MVP Workflows

Status: implementation-oriented baseline for one hospital. Policy choices
tagged as open are recorded in [decisions.md](decisions.md) and must be approved
before feature code depends on them. Examples and tests use synthetic data only.

## Reception

1. Search for a patient before registration using the approved search fields and
   duplicate-matching rules.
2. If no record is selected, collect only approved patient fields and create a
   record with a unique hospital identifier. If candidates exist, staff resolve
   the match under the approved duplicate policy; the application never merges
   records automatically.
3. Correct demographic/contact information through an authorized, auditable
   update. Merge, archive, and permanent deletion remain disabled until their
   policies are approved.
4. Select an approved visit type and doctor, create or update an appointment,
   and record the approved lifecycle event. Schedule conflicts and
   reschedule/cancel outcomes follow owner-approved rules.
5. Check in the patient and place the visit in the configured queue. Queue
   order, priority, and numbering are determined by the approved policy.
6. Create only permitted charges, record an allowed payment, and print the
   resulting receipt. Corrections use approved void/refund/adjustment actions;
   issued records are not silently edited.

Reception can view operational identity, contact, appointment, queue, and
permitted billing fields. Clinical notes, diagnoses, and prescription content
are denied unless a specific minimal workflow field is approved.

## Doctor

1. Authenticate with an individual active staff account.
2. View the doctor's own schedule and patients explicitly within the doctor's
   authorized scope.
3. Open the relevant clinical history and approved allergy/safety information.
   Cross-doctor access is denied unless explicitly granted.
4. Record an encounter, notes, diagnosis, prescription, and approved
   investigation/follow-up details.
5. Save and print a prescription using the approved fields. Clinical corrections
   preserve history and are audited.

The exact consultation fields, diagnosis format, prescription structure, and
clinical-history access rules require product/clinical approval.

## Pharmacy

1. Find the dispensing request by approved prescription lookup and confirm the
   minimum patient identifiers needed to avoid a mismatch.
2. Review only prescription details and allergy/safety information necessary for
   safe dispensing; do not expose general clinical notes.
3. Select available, unexpired batch stock under the approved FEFO and exception
   policy. Record dispensed quantities and stock movement atomically.
4. Record a partial dispense, counter sale, correction, or return only where the
   corresponding policy is approved. Prevent negative stock and preserve the
   movement history.
5. Record pharmacy payment and issue its receipt according to the approved
   relationship between pharmacy sales and the main billing ledger.

The sales ledger, receipt numbering, partial/refill rules, stock adjustment
reasons, quarantine/expiry handling, and return eligibility are owner decisions.

## Administrator

1. Create or invite individual staff accounts through the approved safe initial
   administrator process; deactivate accounts when access should end.
2. Assign only approved Django groups/permissions. Record and audit role and
   sensitive setting changes.
3. Maintain approved departments, visit types, services, charges, payment
   methods, suppliers, medicine reference data, tax/discount settings, and
   numbering configuration.
4. Review reports and approve sensitive financial or inventory actions only
   within an approved authorization limit.

The administrator role does not automatically grant clinical-record access.
Exact settings, approval limits, report definitions, and export permissions
require owner approval.

## Shared lifecycle and integrity rules

- Authentication, authorization, and record scoping are checked on the server
  for reads and writes, including direct URL and POST requests.
- Sensitive operations create an audit event; audit history is not editable by
  normal users.
- Financial and stock effects are transactional, idempotency/duplicate
  submission is handled, and issued history is corrected through explicit
  reversal/adjustment events.
- Exact status names, transition rules, numbering formats, and retention periods
  remain open until approved; no implementation should infer them from these
  workflow summaries.