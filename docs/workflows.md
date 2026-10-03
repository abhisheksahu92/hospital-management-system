# MVP Workflows

Status: implementation-oriented baseline for one hospital. Remaining owner
decisions are recorded in [decisions.md](decisions.md). Examples and tests use
synthetic data only.

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

The current implementation creates the encounter only for the assigned doctor
while the appointment is in progress. Prescription items are optional; if
provided, the prescription is issued atomically with the encounter. Doctors see
their own authored consultation history. Pharmacy can search/print issued
prescriptions with patient ID/name, the safety-notes field, and item instructions,
but cannot open consultation pages or see notes/diagnosis.

## Pharmacy

1. Find the dispensing request by approved prescription lookup and confirm the
   minimum patient identifiers needed to avoid a mismatch.
2. Review only prescription details and allergy/safety information necessary for
   safe dispensing; do not expose general clinical notes.
3. Select unexpired, non-quarantined stock; FEFO is the default suggestion.
   Dispensing quantity is cumulative against the prescription and cannot exceed
   its remaining quantity. Stock is locked and updated atomically.
4. Counter sales are permitted only for medicines explicitly marked OTC. Both
   counter sales and prescription dispensings create an invoice in the shared
   financial ledger; Pharmacy does not record payments.
5. Stock adjustments require a reason and create both a movement and audit
   event. Quarantined/expired stock is excluded from sale and dispensing.
6. Return requests reference the original sale or dispensing line and reserve
   no more than its unreturned quantity. Requests remain pending until handled
   by an Administrator. Returned medicine is not automatically returned to
   sellable stock; any restock requires an explicit, separately audited action.

## Administrator

1. Create or invite individual staff accounts through the approved safe initial
   administrator process; deactivate accounts when access should end.
2. Assign only approved Django groups/permissions. Record and audit role and
   sensitive setting changes.
3. Maintain approved departments, visit types, services, charges, payment
   methods, suppliers, medicine reference data, tax/discount settings, and
   numbering configuration.
4. Review reports and perform discounts, refunds, invoice voids, and financial
   adjustments with a reason and audit record. The single-hospital MVP does not
   require a second approver.

The administrator role does not automatically grant clinical-record access.
Exact settings, approval limits, report definitions, and export permissions
require owner approval.

## Appointment implementation baseline

Pending owner confirmation, the current workflow treats an exact doctor/start
time collision as a conflict and rejects it; appointment duration, overlapping
intervals, and overbooking are not inferred. Reception may book/reschedule a
scheduled visit, check in or cancel a scheduled/checked-in visit, and mark a
scheduled visit no-show. A doctor may start a checked-in visit and complete an
in-progress visit. The waiting queue contains checked-in visits ordered by
check-in timestamp, then record ID; no queue number or priority is assigned.
All lifecycle changes are recorded with actor, previous/next status, and time.

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