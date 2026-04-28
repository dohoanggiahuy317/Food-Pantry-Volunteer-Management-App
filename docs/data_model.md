# Data Model and Database Flow

This document describes the data model, database schema, and runtime behavior of the volunteer management app backend, including how shifts, users, signups, and notifications are structured and managed in MySQL. It also covers concurrency safety measures for critical operations like signup creation and shift editing, as well as handling for recurring shifts and pantry subscriptions. The goal is to provide a clear reference for developers working on the backend and to explain the rationale behind key design decisions.

## Goal
Run the app on MySQL by default, with automatic schema creation and automatic seed data load when the database is empty.

## Runtime behavior
At backend startup:

1. `backend/app.py` loads env and calls backend factory.
2. `backend/backends/factory.py` chooses `DATA_BACKEND` (default: `mysql`).
3. For MySQL mode:
   - `backend/db/init_schema.py` applies all SQL files in `backend/db/migrations/` in filename order (idempotent `CREATE TABLE IF NOT EXISTS` schema baseline).
   - `backend/backends/mysql_backend.py` is initialized.
   - If DB is empty and `SEED_MYSQL_FROM_JSON_ON_EMPTY=true`, seed data is loaded from `backend/data/mysql.json`.
4. API routes continue using the same request/response contract as before.
5. `backend/app.py` can call `backend/notifications/notifications.py` to send Resend emails for confirmed signups, shift updates that require reconfirmation, shift cancellations, pantry-subscriber new-shift notifications, and shift help broadcasts.
6. User timezone is detected in the browser, persisted on the `users` row, and reused by the backend when rendering email times.

## Configuration (`backend/.env`)
- `DATA_BACKEND=mysql`
- `MYSQL_HOST=127.0.0.1`
- `MYSQL_PORT=3306`
- `MYSQL_DATABASE=volunteer_managing`
- `MYSQL_USER=volunteer_user`
- `MYSQL_PASSWORD=volunteer_pass`
- `MYSQL_POOL_SIZE=5`
- `MYSQL_CONNECT_TIMEOUT=10`
- `SEED_MYSQL_FROM_JSON_ON_EMPTY=true`
- `RESEND_API_KEY=<your resend api key>`
- `RESEND_FROM_EMAIL=noreply@updates.example.com`

## Notification flow

- `backend/notifications/notifications.py` is a service module, not a Flask route module.
- It returns a structured notification result payload:
  - `ok`
  - `code`
  - `message`
  - `recipient_email`
  - `subject`
  - `provider_response`
- `backend/app.py` uses that payload to log skipped or failed email sends without interrupting the signup or shift-management API response.
- Current notification scenarios:
  - confirmed signup
  - shift update / reconfirmation required
  - shift cancellation
  - pantry subscriber notified when a pantry creates a new one-off shift or recurring series
  - shift help broadcast to selected volunteers when a shift needs extra coverage
- Notification times are localized with Python `zoneinfo` from the saved `users.timezone` value, with `America/New_York` as the fallback.

## Resend domain note

- Resend requires a domain you control for sending and recommends using a subdomain such as `updates.yourdomain.com`.
- If your team does not already own a domain, register one first, add it to Resend, then follow Resend’s DNS verification steps with your DNS provider before setting `RESEND_FROM_EMAIL`.

## MySQL schema
Defined in `backend/db/migrations/001_initial.sql`:

- `roles`
- `users`
- `user_roles`
- `pantries`
- `pantry_leads`
- `pantry_subscriptions`
- `shift_series`
- `shifts`
- `shift_roles`
- `shift_signups`
- `help_broadcasts`

Important constraints:
- `roles.role_id` is seeded explicitly; the protected `SUPER_ADMIN` role uses `role_id = 0`.
- `users.email` is unique.
- `users.auth_uid` is unique when present and is used to link Firebase users to local accounts.
- `user_roles` and `pantry_leads` use composite primary keys.
- `pantry_subscriptions` uses composite primary key `(pantry_id, user_id)` so each volunteer can subscribe to a pantry only once.
- `shift_signups` has unique `(shift_role_id, user_id)` to prevent duplicate signups.
- `shift_signups` stores `reservation_expires_at` for 48-hour reconfirmation reservation windows.
- `shift_signups` has index `idx_shift_signups_role_status_reservation (shift_role_id, signup_status, reservation_expires_at)` for reservation-aware capacity checks.
- `help_broadcasts` stores shift help broadcast history with the sender, target shift, recipient count, and send timestamp.
- `shift_series` stores recurring weekly schedule metadata (`timezone`, `interval_weeks`, `weekdays_csv`, finite end rule).
- `shifts.shift_series_id` is nullable so one-off shifts remain simple while recurring occurrences link back to a series.
- `shifts.series_position` preserves the occurrence order inside the current recurring slice.
- Foreign keys enforce cascade cleanup for dependent records.
- `shifts.created_by` is nullable and uses `ON DELETE SET NULL`, so deleting a user does not block on shifts they created.
- `pantry_subscriptions` cascades on both pantry and user deletion.

Current user/account fields:
- `users` stores `full_name`, `email`, `phone_number`, `timezone`, `auth_provider`, `auth_uid`, `attendance_score`, `created_at`, and `updated_at`.
- There is no `is_active` flag in the runtime schema; accounts are either present or deleted.
- The current admin-management flow treats each user as having one editable system role at a time (`VOLUNTEER`, `PANTRY_LEAD`, or `ADMIN`), while the protected seeded `SUPER_ADMIN` account is fixed and not editable through the app.

Account lifecycle notes:
- Firebase mode uses Google sign-in and links users by Firebase UID after the first successful login.
- Firebase Google signup can store the detected browser timezone immediately.
- Verified email changes are initiated client-side with a fresh Google reauthentication, then the backend syncs the new verified email by UID.
- The frontend also syncs the detected browser timezone through `PATCH /api/me` after authenticated app boot when it is missing or changed.
- Account deletion deletes the linked Firebase user first and then removes the local user row.
- The protected seeded `SUPER_ADMIN` account (`user_id = 1`) cannot delete itself.

## Concurrency safety
`backend/backends/mysql_backend.py` uses transactions for signup creation, full shift/role replacement, and reconfirmation:

- Locks `shift_roles` row with `SELECT ... FOR UPDATE`.
- Checks duplicate signup and reservation-aware capacity inside transaction.
- Inserts signup and updates `filled_count/status` atomically.
- Full shift edit path updates the shift, upserts submitted roles, and soft-cancels omitted roles with signups inside one transaction.
- Reconfirm path locks signup + role (+ shift checks) so reduced-capacity reconfirmation is first-come-first-serve without overbooking.

Recurring-series note:
- Recurring creation and future-scope recurring edits/cancels are orchestrated in `backend/app.py` and still operate on concrete shift rows.
- The current backend contract persists recurring metadata through `shift_series`, `shifts.shift_series_id`, and `shifts.series_position`.
- Manager-facing payloads expose `is_recurring`, `shift_series_id`, `series_position`, and `recurrence` metadata for edit flows.

Pantry-subscription note:
- The volunteer pantry directory is backed by user-specific pantry payloads that include `is_subscribed`, `upcoming_shift_count`, and `preview_shifts`.
- New-shift subscriber emails are triggered only on shift creation routes. One-off create sends one email per subscriber; recurring create sends one summary email per subscriber for the full series.

## File roles
- `backend/backends/base.py`: storage interface.
- `backend/backends/memory_backend.py`: legacy in-memory backend.
- `backend/backends/mysql_backend.py`: MySQL backend.
- `backend/backends/factory.py`: backend selection + startup initialization/seed.
- `backend/notifications/notifications.py`: volunteer email notification service and structured notification result builder, including help broadcasts.
- `backend/db/mysql.py`: MySQL connection pool.
- `backend/db/init_schema.py`: schema application at startup.
- `backend/db/migrations/001_initial.sql`: table/index/FK definitions.
- `backend/db/seed.py`: seed import helper (`mysql.json` -> MySQL).
- `backend/data/mysql.json`: MySQL seed dataset, including the expanded future mock shift schedule.
- `backend/data/in_memory.json`: in-memory backend seed dataset.

Dev note:
- This branch keeps account and recurring-shift schema changes in `001_initial.sql`. Recreate older dev databases if they were initialized before the current auth/timezone/recurring-shift model.
