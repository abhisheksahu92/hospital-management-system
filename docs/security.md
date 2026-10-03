# Security Baseline

## Staff authentication

- Django's built-in authentication stores password hashes; there is no public
  staff-registration route. The first administrator is created interactively
  with `createsuperuser`.
- Staff role membership is managed server-side through Django Groups. Normal
  staff cannot access Django Admin or edit roles through a profile field.
- Inactive accounts cannot authenticate; Django's authentication backend also
  rejects their existing sessions on the next request.
- CSRF middleware protects form posts. Session cookies are secure when
  `DJANGO_DEBUG=false`, and staff sessions expire at browser close or after the
  configured eight-hour maximum.
- Password-reset responses do not reveal whether an email belongs to an
  account. Development prints reset mail to the console; non-debug settings use
  SMTP with the Resend API key from `RESEND_KEY` and a configured verified
  `RESEND_FROM_EMAIL`.

## Staging handoffs

Django's built-in login view does not rate-limit failed attempts. Staging and
production must have edge-level login rate limiting and monitoring for repeated
failures configured and verified under KAN-16 before real staff accounts are
used. Do not rely on a client-side control for this protection.

Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, a verified sender address, and
the mail secret in the deployment environment. Never put production credentials
in source control or use real patient data in development/tests. This baseline
is not a legal compliance claim; privacy, retention, hosting region, and vendor
reviews remain separate requirements.