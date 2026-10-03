# MVP Requirements

Status: workflow baseline for product-owner review. Business rules marked as
open in [decisions.md](decisions.md) must be approved before they are encoded.

## Product scope

The first release serves one hospital in India with approximately 50 staff. It
covers outpatient reception, appointments and queue, doctor consultations and
prescriptions, billing and payments, pharmacy inventory/dispensing/sales, staff
administration, and operational reports.

Inpatient admission, beds/wards, nursing, laboratory, radiology, operating
theatre, insurance/TPA, patient portal, payroll/HR, accounting/ERP, messaging,
multi-hospital tenancy, and advanced analytics are out of scope unless separately
approved and ticketed.

## Roles and data access

Access is enforced server-side for every request, including direct URLs and
POSTs. A role shown in the interface is not an authorization boundary. Access
to an individual patient's record is separately scoped where applicable.

| Action or information | Reception | Doctor | Pharmacy | Administrator |
|---|---|---|---|---|
| Register/search patients and edit demographics/contact | Yes | No by default | No | Configuration only; no routine clinical access |
| Appointments, check-in, queue | Manage operational workflow | View own/authorized schedule and assigned patients | Minimum dispensing workflow only | Configure operational settings; reports as authorized |
| Clinical notes and diagnosis | No | Assigned/otherwise authorized patients | No | No by default |
| Prescriptions | No, except explicitly approved workflow fields | Create/view for authorized patients | Minimum prescription details needed to dispense | No by default |
| Allergy/safety information | Only if a specific reception workflow is approved | Relevant authorized clinical workflow | Relevant safety information required for dispensing | No by default |
| Invoices, payments, receipts | Permitted collection workflow | No by default | Pharmacy payment workflow only | Approved financial reports and controlled approvals |
| Catalogue, suppliers, batches, stock, dispensing, returns | No | No | Manage pharmacy operations | Oversight/report access as approved |
| Staff, roles, hospital settings, numbering | No | No | No | Manage, with sensitive changes audited |

"No by default" means denied until a documented requirement grants the minimum
necessary access. Administrator status does not itself grant unrestricted
clinical access. Cross-doctor access is denied unless explicitly authorized.
The detailed policy and test matrix belong to KAN-4/KAN-15.

## User stories and acceptance criteria

### Patient registration and search

As reception staff, I can find an existing patient before registering or
updating one, so duplicate records are not created casually.

- Search only returns patients the current staff member may access.
- A new record receives a unique hospital identifier using the approved format.
- Duplicate candidates are presented according to owner-approved matching
  rules; the system does not silently merge records.
- Demographic/contact corrections preserve an audit trail and follow the
  approved correction/archive policy.
- Only approved, necessary patient information is collected and shown to each
  role.

### Appointments and queue

As reception staff, I can book and manage a visit and check a patient in; as a
doctor, I can see my authorized schedule and waiting patients.

- Appointment types, states, scheduling constraints, and lifecycle timestamps
  follow the approved policy.
- Reschedule, cancellation, check-in, no-show, completion, and conflict outcomes
  are explicit and audited as configured.
- Queue order/number is generated consistently using the approved rule and
  cannot be changed by an unauthorized request.
- A doctor cannot access another doctor's patients outside the approved scope.

### Consultation and prescription

As a doctor, I can record an authorized encounter, clinical note, diagnosis,
prescription, and approved follow-up information.

- Clinical fields and diagnosis representation are limited to the approved MVP
  set.
- Prescription items capture the approved medicine, dose/instructions, and
  dispensing-related details.
- Reception cannot read or change clinical notes, diagnosis, or prescription
  content.
- Pharmacy sees only the patient identity, relevant safety information, and
  prescription details needed for dispensing.
- A printable prescription contains only approved information.

### Billing and payment

As authorized staff, I can create permitted charges, record payments, and issue
receipts; corrections use controlled, auditable operations.

- Money uses decimal amounts; payment, invoice, and receipt records are not
  silently overwritten or deleted.
- Partial payment, discount, tax, void, refund, adjustment, approval, and refund
  destination behavior follow the approved financial policy.
- Duplicate submissions and invalid amounts cannot create duplicate financial
  effects.
- Users can access only the financial actions and records allowed by their role.

### Pharmacy inventory and dispensing

As pharmacy staff, I can receive and manage batch-tracked stock, dispense a
prescription, record approved counter sales, and process authorized returns.

- Stock receipts, batches, expiry, quantities, prices, and stock movements are
  traceable; stock cannot become negative through normal workflows.
- Expired or unavailable stock cannot be dispensed. Batch selection follows the
  approved FEFO/exception policy.
- Partial dispensing, OTC/counter sales, returns, corrections, and their
  relationship to hospital billing follow approved policy.
- Patient visibility is limited to the minimum needed for safe dispensing.

### Administration and reports

As an administrator, I can manage staff lifecycle and approved operational
settings, and review role-appropriate reports.

- Staff accounts are individual; disabled staff cannot authenticate or perform
  operations.
- Role changes and sensitive settings are authorized and audited.
- Reports use approved definitions, filters, date boundaries, and export rights.
- Reports do not expose clinical or personal information beyond the viewer's
  role.

## Data minimization and synthetic examples

Collect only fields approved as necessary for an outpatient workflow. Candidate
patient fields include hospital ID, name, date-of-birth/age representation,
contact details, address, emergency contact, and approved safety/allergy data.
Sex/gender, blood group, and any additional sensitive field require a documented
operational need. Use synthetic data in development, tests, and documentation.

## Cross-cutting requirements

- Use server-side authentication, role permissions, and object-level scope.
- Audit sensitive clinical, identity, configuration, inventory, and financial
  changes without recording passwords, tokens, or other secrets.
- Preserve historical transaction values; corrections are new controlled
  events.
- Protect payments, stock operations, numbering, and state changes with database
  constraints and transactions.
- Use accessible, keyboard-friendly Django templates and print layouts; do not
  add a SPA or infrastructure without an approved requirement.
- Retention, consent/notice, hosting/data region, backups/recovery targets, and
  vendor responsibilities require owner/security review; this specification
  does not claim legal compliance.

## External services

The application foundation uses Django and PostgreSQL as its intended data
architecture. Supabase is not connected. Its possible role, if any, is an open
owner decision in [decisions.md](decisions.md); no hospital data may be exposed
to it before approval and a security review.