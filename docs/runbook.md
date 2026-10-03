# Non-Production Deployment, Backups, and Operational Runbook (KAN-18)

This document establishes the deployment, backup, recovery, and operational procedures for staging and production readiness.

## Staging Deployment Architecture

- **Application Host**: Render Web Service (Python/Gunicorn running Django).
- **Database**: PostgreSQL (managed via Supabase or Render Postgres).
- **DNS, SSL & Edge Security**: Cloudflare (SSL Full/Strict, HTTP/2, edge rate limiting on `/accounts/login/`).
- **Error Monitoring**: Sentry (configured via `SENTRY_DSN` with environment tagging).
- **Uptime Monitoring**: External synthetic HTTP check targeting `/health/` every 5 minutes.

### Required Environment Configuration

| Variable | Staging Setting | Description |
|---|---|---|
| `DJANGO_DEBUG` | `false` | Disables debug mode and activates security headers |
| `DJANGO_SECRET_KEY` | *Secret* | Long random cryptographic key |
| `DJANGO_ALLOWED_HOSTS` | `*.onrender.com,your-domain.com` | Whitelist of valid Host headers |
| `DATABASE_URL` | `postgresql://...` | Connection pooling URL for PostgreSQL |
| `RESEND_KEY` | *Secret* | Transactional email API key |
| `RESEND_FROM_EMAIL` | `noreply@hospital-domain.com` | Verified sending identity |
| `SENTRY_DSN` | `https://...@sentry.io/...` | Sentry exception tracking |

### Staging Deployment Steps

1. Configure environment variables in the Render Dashboard.
2. Build command:
   ```sh
   pip install -r requirements.txt && python manage.py collectstatic --noinput
   ```
3. Start command:
   ```sh
   python manage.py migrate && python manage.py bootstrap_hospital && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
   ```
4. Verify deployment:
   - Hit `/health/` to ensure HTTP 200 `{"status": "ok"}`.
   - Verify static assets load properly.

---

## Backup and Recovery Procedures

### Automated Database Backups

- **Daily Logical Backups**: Automated daily `pg_dump` snapshot retained for 30 days.
- **Continuous Write-Ahead Logging (WAL)**: Point-in-time recovery (PITR) enabled where supported by the managed provider.
- **Encryption**: Backups encrypted at rest (AES-256) and in transit (TLS 1.3).
- **Access Restrictions**: Direct database and backup access restricted to authorized DevOps personnel with MFA.

### Backup Verification & Restore Drill

1. Restore drill must use synthetic test data only; never run restore tests with live clinical data.
2. Restore command:
   ```sh
   pg_restore --clean --no-acl --no-owner -h <restore_host> -U <user> -d <target_db> <backup_file>.dump
   ```
3. Post-restore verification:
   - Run `python manage.py check`.
   - Validate record counts on `core_patient`, `core_appointment`, `core_invoice`, and `core_medicinebatch`.
   - Verify transaction sequence counters (`core_numbersequence`).

### Recovery Objectives

- **Recovery Point Objective (RPO)**: <= 1 hour (maximum data loss window).
- **Recovery Time Objective (RTO)**: <= 2 hours (maximum service restoration time).

---

## Operational Runbook & Incident Response

### Deployment Rollback Checklist

If a bad migration or breaking regression is detected post-deployment:
1. Revert Git repository to the last known stable commit tag.
2. Trigger immediate redeploy on Render.
3. If database schema was altered, apply reverse migration (`python manage.py migrate <app> <target_migration>`) or restore database snapshot from pre-deployment backup.
4. Test `/health/` and role logins to confirm recovery.

### Go-Live Checklist (Production Readiness Gate)

Production launch remains strictly blocked until the following are confirmed:
- [ ] Security review completed (RBAC boundaries, CSRF, login throttling).
- [ ] Audit logging verified for all sensitive record reads/writes.
- [ ] Staging and production databases completely isolated; zero real patient data in non-production.
- [ ] Backup and restore drill successfully tested and timed.
- [ ] Sentry alerting and external `/health/` uptime monitors active.
- [ ] HTTPS enforced across all routes with HSTS enabled.
- [ ] Hospital operational settings and number sequences verified.
