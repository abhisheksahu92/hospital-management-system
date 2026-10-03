# Initial Data Model

KAN-8 schema baseline for one hospital. Django models and migrations are the
source of truth; PostgreSQL is the intended production database, with SQLite
for local development/tests. No Supabase tables or client are configured.

## Entity inventory

| Entity | Key fields and relationships | Constraints and indexes |
|---|---|---|
| Django `User`, `Group`, `Permission` | Built-in authentication and group membership | Django-managed tables and constraints |
| `StaffProfile` | user, employee_id, department, job_title | Unique user and employee_id |
| `Department` | code, name, is_active | Unique code and name |
| `HospitalSettings` | name, timezone, currency_code, phone, address | Primary key constrained to singleton value 1 |
| `NumberSequence` | code, prefix, next_value | Unique code; next_value > 0 |
| `VisitType` | code, name, is_active | Unique code and name |
| `Service` | code, name, optional current_charge, is_active | Unique code/name; configured charge >= 0 |
| `PaymentMethod` | code, name, is_active | Unique code and name |
| `Supplier` | code, name, contact fields, address, is_active | Unique code |
| `Medicine` | code, generic/brand names, strength, form, unit, optional barcode | Unique code and non-null barcode |
| `Patient` | mrn, full_name, date_of_birth, contact, emergency contact, safety notes, archived_at | Unique mrn; `patient_name_idx` |
| `Appointment` | patient, doctor, visit_type, scheduled_at, status, queue_number, lifecycle times | Allowed-status check; time/status, doctor/time, and patient/time indexes |
| `Consultation` | patient, doctor, optional one-to-one appointment, clinical_notes, diagnosis | Appointment one-to-one; patient/doctor protected |
| `Prescription` | number, patient, doctor, optional consultation, status, issued_at | Unique number; allowed-status check |
| `PrescriptionItem` | prescription, medicine, dosage, frequency, duration, instructions, quantity | quantity > 0 |
| `StockReceipt` | number, supplier, supplier_reference, received_at, received_by | Unique number |
| `MedicineBatch` | medicine, receipt, batch_number, expiry_date, prices, received/on-hand quantities | Unique medicine+batch; nonnegative prices; 0 <= on-hand <= received; FEFO index |
| `StockMovement` | batch, kind, quantity_delta/before/after, reference, actor, created_at | Nonzero delta; nonnegative balances; after = before + delta; batch/time index |
| `PharmacySale` | number, optional patient, status, sold_at, sold_by | Unique number; allowed-status check |
| `PharmacySaleLine` | sale, batch, quantity, unit_price, line_total | quantity > 0; amounts >= 0 |
| `Dispensing` | number, prescription, patient, dispensed_by, status, dispensed_at | Unique number; allowed-status check |
| `DispensingLine` | dispensing, prescription_item, batch, quantity, unit_price | quantity > 0; unit_price >= 0 |
| `PharmacyReturn` | number, optional patient, reason, status, created_by | Unique number; allowed-status check |
| `ReturnLine` | pharmacy_return, exactly one sale_line or dispensing_line, quantity, refund_amount | Source cardinality check; quantity > 0; refund_amount >= 0 |
| `Invoice` | number, patient, status, subtotal/tax/discount/total snapshots, issued_at, created_by | Unique number; totals >= 0; allowed-status check |
| `InvoiceLine` | invoice, optional service, description, quantity, unit_price, optional tax_rate, discount_amount, line_total | quantity > 0; monetary values/configured rate >= 0 |
| `Payment` | invoice, method, amount, reference, received_by, received_at | amount > 0 |
| `Refund` | payment, amount, reason, status, requester, approver | amount > 0; allowed-status check |
| `Adjustment` | invoice, signed amount, reason, approver | amount != 0 |
| `AuditEvent` | actor, action, target type/id, details, created_at | Timestamp index; actor may be null for system events |

Mutable reference/workflow rows inherit `created_at` and `updated_at`; stock
movements and audit events are timestamped event records. Foreign-key deletion
behavior is `PROTECT` for records whose history must survive, and `SET_NULL`
only for optional actor/department attribution.

## Relationships

- Django `User`, `Group`, and `Permission` provide identity and role primitives.
  `StaffProfile` is one-to-one with User; role membership stays in Django
  Groups. `Department` optionally groups staff.
- `HospitalSettings` is constrained to one row. `NumberSequence` stores one
  counter per document kind; KAN-23 will make allocation transaction-safe.
- `Patient` owns `Appointment`, `Consultation`, `Prescription`, and `Invoice`
  history. `Appointment` references a doctor (`StaffProfile`) and `VisitType`;
  `Consultation` references its patient, doctor, and optionally one appointment.
- `Prescription` belongs to a patient/doctor and optionally a consultation;
  `PrescriptionItem` references a medicine.
- `Supplier` owns `StockReceipt`; each `MedicineBatch` belongs to a medicine
  and receipt. `StockMovement` records before/delta/after quantities against a
  batch. `Dispensing` and its lines preserve dispensing separately from the
  prescription; `PharmacySale` and its lines preserve counter-sale snapshots.
  `PharmacyReturn`/`ReturnLine` refer to exactly one sale or dispensing line.
- `InvoiceLine` preserves description, quantity, unit price, tax, discount, and
  total snapshots. `Payment` references a `PaymentMethod`; `Refund` references
  a payment and `Adjustment` references an invoice.
- `AuditEvent` stores actor (nullable for system events), action, target, time,
  and structured metadata. Append-only behavior and restricted access are
  enforced by later service/security work, not by this table alone.

## Integrity

Business identifiers are unique. Patient, financial, and stock history uses
`PROTECT` foreign keys rather than cascading deletion. Amounts use decimal
fields; positive/nonnegative quantities and amounts, the singleton settings row,
batch stock bounds, movement arithmetic, and return-line source cardinality have
database constraints. Search/schedule/expiry lookups have targeted indexes.

Issued invoice lines and pharmacy sale lines store the values applied at issue
time, so changing current service or medicine prices does not rewrite history.
Operational services in KAN-23 will coordinate stock, payments, returns, and
number generation transactionally; `core.services.numbering.next_number()` uses
a row lock and atomic update for document sequences, while KAN-23 adds the
remaining concurrency/invariant coverage. A schema constraint alone cannot enforce
cross-row totals or prevent every concurrent oversell.

## Explicitly deferred pending owner decisions

- Separate `PatientAllergy` table, demographic sex/gender fields, and the final
  patient matching/archive policy.
- Investigation/follow-up structures; clinical and prescription field detail.
- Tax/HSN rules, discount approval policy, pharmacy/main-ledger relationship,
  OTC rules, return eligibility, and exact document prefixes/number formats.
- Doctor schedule overlap policy and queue numbering/order.

The current schema uses one patient safety-notes field, a service's current
charge (nullable until the charge policy is approved) plus transaction snapshots,
an optional invoice tax-rate snapshot (nullable until tax rules are approved),
and general number-sequence rows. These are reversible MVP foundations, not
approval of the deferred business policies.