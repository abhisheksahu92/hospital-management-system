# Hospital Management System

An outpatient hospital operations system for a single hospital. The application
uses Django templates and the Django ORM; it does not connect to Supabase.

## Development setup

Requirements: Python 3.12 or newer and pip. PostgreSQL is optional for local
smoke testing; SQLite is used by default. To use PostgreSQL, set `DATABASE_URL`
in `.env`.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

If `.env` already exists, do not overwrite it; merge the required settings from
`.env.example` into it. Open http://127.0.0.1:8000/ for the home page and
http://127.0.0.1:8000/health/ for the health check.

## Configuration

Settings are read from environment variables, with `.env` loaded for local
development. `.env.example` contains only local placeholders. Set
`DJANGO_SECRET_KEY` to a unique secret and set `DJANGO_DEBUG=false` outside local
development. Set `DJANGO_ALLOWED_HOSTS` to a comma-separated host list when
deploying.

For PostgreSQL, use a URL such as:

```dotenv
DATABASE_URL=postgresql://hospital:change-me@localhost:5432/hospital
```

Never commit `.env`, production credentials, uploaded files, local databases, or
patient data.

## Development commands

```sh
python manage.py check
python manage.py test
ruff check .
ruff format --check .
```

Runtime and development dependencies are pinned in `requirements.txt` and
`requirements-dev.txt`; update pins intentionally and verify them with CI.

## Staff accounts

Create the first administrator interactively; the application has no default
credentials or public staff-registration page:

```sh
python manage.py migrate
python manage.py createsuperuser
```

Sign in at `/accounts/login/` and use Django Admin at `/admin/` to create
individual staff accounts and profiles. Assign role groups only through the
server-side admin; deactivate accounts with Django's `is_active` field rather
than deleting them. Local password-reset emails use the console backend. With
`DJANGO_DEBUG=false`, SMTP is configured for Resend using `RESEND_KEY` and
`RESEND_FROM_EMAIL`; set the latter to a verified sender before staging use. No
email is sent by the test suite. Django's built-in login view does not
rate-limit failures; configure and verify edge-level login rate limiting under
KAN-16 before staging accounts are used. See [docs/security.md](docs/security.md).

After creating the initial administrator, run `python manage.py bootstrap_hospital`
to create the singleton hospital settings placeholder, four empty role groups,
and document-number sequences. Replace the placeholder hospital name and review
group permissions before staff onboarding. Run the command again safely after
deployment or restore; it does not create users or assign permissions. Configure
departments, visit types, services, payment methods, suppliers, and medicines in
Django Admin. Tax, discount, refund, and pharmacy pricing policies remain subject
to the open decisions in `docs/decisions.md`.

## Supabase

Supabase is not configured or connected. Its intended role (if any), data access
model, and security responsibilities remain an open product/architecture
decision. Django and PostgreSQL are the application direction for this MVP;
do not migrate or expose hospital data through Supabase until that decision is
approved.