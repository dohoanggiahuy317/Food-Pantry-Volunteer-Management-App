# Data Model and Database Flow

## Goal
Run the app on MySQL by default, with automatic schema creation and automatic seed data load when the database is empty.

## Runtime behavior
At backend startup:

1. `backend/app.py` loads env and calls backend factory.
2. `backend/backends/factory.py` chooses `DATA_BACKEND` (default: `mysql`).
3. For MySQL mode:
   - `backend/db/init_schema.py` applies all SQL files in `backend/db/migrations/` in filename order (idempotent `CREATE TABLE IF NOT EXISTS` schema baseline).
   - `backend/backends/mysql_backend.py` is initialized.
   - If DB is empty and `SEED_MYSQL_FROM_JSON_ON_EMPTY=true`, seed data is loaded from `backend/data/db.json`.
4. API routes continue using the same request/response contract as before.

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

## MySQL schema
Defined in `backend/db/migrations/001_initial.sql`:

- `roles`
- `users`
- `user_roles`
- `pantries`
- `pantry_leads`
- `shifts`
- `shift_roles`
- `shift_signups`

Important constraints:
- `users.email` is unique.
- `user_roles` and `pantry_leads` use composite primary keys.
- `shift_signups` has unique `(shift_role_id, user_id)` to prevent duplicate signups.
- `shift_signups` stores `reservation_expires_at` for 48-hour reconfirmation reservation windows.
- `shift_signups` has index `idx_shift_signups_role_status_reservation (shift_role_id, signup_status, reservation_expires_at)` for reservation-aware capacity checks.
- Foreign keys enforce cascade cleanup for dependent records.

## Concurrency safety
`backend/backends/mysql_backend.py` uses transactions for signup creation and reconfirmation:

- Locks `shift_roles` row with `SELECT ... FOR UPDATE`.
- Checks duplicate signup and reservation-aware capacity inside transaction.
- Inserts signup and updates `filled_count/status` atomically.
- Reconfirm path locks signup + role (+ shift checks) so reduced-capacity reconfirmation is first-come-first-serve without overbooking.

## File roles
- `backend/backends/base.py`: storage interface.
- `backend/backends/memory_backend.py`: legacy in-memory backend.
- `backend/backends/mysql_backend.py`: MySQL backend.
- `backend/backends/factory.py`: backend selection + startup initialization/seed.
- `backend/db/mysql.py`: MySQL connection pool.
- `backend/db/init_schema.py`: schema application at startup.
- `backend/db/migrations/001_initial.sql`: table/index/FK definitions.
- `backend/db/seed.py`: seed import helper (`db.json` -> MySQL).
- `backend/data/db.json`: initial seed dataset.
