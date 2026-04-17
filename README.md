# Volunteer Management System

An application for managing volunteer shifts at food pantries. Pantry leads and admins create and manage shifts; volunteers and the public can browse open shifts by pantry.

---

## Goals and Purpose:

We aim to build a robust, secure, and user-friendly volunteer management system that streamlines shift scheduling and communication for food pantries. This project serves as a practical demonstration of full-stack development skills, including backend API design, frontend development, database management, authentication integration, and email notifications. The application solves real-world problems faced by volunteer organizations, such as coordinating schedules, managing user roles, and sending timely notifications.

---

## Tech Stack

| Layer               | Technology                                                                                                 |
| :------------------ | :--------------------------------------------------------------------------------------------------------- |
| Backend             | Python 3, Flask                                                                                            |
| Frontend            | Vanilla JS, HTML, CSS                                                                                      |
| Database            | in-memory or MySQL 8.4 (containerized via Docker)                                                          |
| Auth                | in-memory demo auth or Firebase Authentication with Google sign-in. Flask uses session cookies after login |
| Email notifications | Resend API for signup confirmation, shift update, shift cancellation, and pantry-subscriber new-shift emails |

---

## Architecture & API Design

### Backend Factory Pattern

The data layer uses an abstract `StoreBackend` interface with two concrete implementations:

- **`MySQLBackend`** — production backend; connects to the MySQL Docker container.
- **`MemoryBackend`** — in-memory backend backed by plain Python dicts; no database required. Useful for isolated testing.

The active backend is selected at startup via the `DATA_BACKEND` environment variable (defaults to `mysql`). Swapping backends requires no changes to `app.py`.

### Test Layout

- Automated tests live in the repository-level `tests/` directory.
- `tests/conftest.py` adds `backend/` to the Python import path so tests can still import `app`, `backends`, and `notifications` while being run from the repo root.
- Current test files include `tests/test_notifications.py` and `tests/test_signup_rate_limit.py`.

### Auth Provider Switch

Authentication is configured separately from data storage:

- **`AUTH_PROVIDER=memory`** — sample accounts for local login/logout testing.
- **`AUTH_PROVIDER=firebase`** — Google sign-in with Firebase Authentication, verified server-side through the Firebase Admin SDK.

After a successful login or signup, Flask stores the authenticated local user in a session cookie and all protected API routes use that session.

### Notification Flow

- `backend/notifications/notifications.py` is the shared email service layer for volunteer notifications.
- `app.py` sends notification emails for 4 scenarios:
  - signup confirmed (optional due to rate-limit)
  - shift updated and reconfirmation required
  - shift cancelled (optional due to rate-limit)
  - pantry subscriber notified when a pantry posts a new one-off shift or recurring series
- Shift times in emails are formatted from UTC into the saved `users.timezone` value when available, with `America/New_York` as the fallback.
- The notification service returns a structured result payload with `ok`, `code`, `message`, `recipient_email`, `subject`, and `provider_response`.
- `app.py` logs warning details when the email is skipped or fails, instead of mixing Flask `jsonify(...)` responses into the notification helper.

### Timezone Handling

- Shift timestamps are stored in UTC in the backend and API responses remain ISO-8601 UTC strings.
- The web app detects the browser timezone with `Intl.DateTimeFormat().resolvedOptions().timeZone`.
- After authenticated app boot, the frontend syncs that timezone into the current user profile through `PATCH /api/me` when it is missing or changed.
- Google signup includes the browser timezone so new volunteer accounts start with a saved timezone immediately.
- The UI renders shift times in the browser's local timezone, while notification emails use the saved timezone on the user record.

### Core API Routes

| Method   | Route                                | Description                                                                       |
| :------- | :----------------------------------- | :-------------------------------------------------------------------------------- |
| `GET`    | `/api/auth/config`                   | Get active auth mode and safe browser config                                      |
| `POST`   | `/api/auth/login/google`             | Log in an existing local user with Google/Firebase                                |
| `POST`   | `/api/auth/signup/google`            | Create a volunteer account after Google auth, including optional browser timezone |
| `POST`   | `/api/auth/login/memory`             | Log in with a sample in-memory account                                            |
| `POST`   | `/api/auth/logout`                   | Clear the current session                                                         |
| `GET`    | `/api/me`                            | Get current user with roles and saved timezone                                    |
| `PATCH`  | `/api/me`                            | Update the current user's basic profile fields, including saved timezone          |
| `POST`   | `/api/me/email-change/prepare`       | Validate a pending Firebase-backed email change                                   |
| `DELETE` | `/api/me`                            | Delete the current user's local account and linked Firebase account               |
| `GET`    | `/api/users`                         | List users for admin-capable actors, with optional `q` and `role` filters         |
| `GET`    | `/api/users/<id>`                    | Get a full user profile for the Admin Users tab                                   |
| `PATCH`  | `/api/users/<id>/roles`              | Replace a user's single editable role                                             |
| `GET`    | `/api/pantries`                      | List pantries accessible to current user                                          |
| `GET`    | `/api/pantries/<id>/shifts`          | List all shifts for a pantry (admin/lead view)                                    |
| `GET`    | `/api/pantries/<id>/active-shifts`   | List non-expired shifts (public/volunteer view)                                   |
| `GET`    | `/api/volunteer/pantries`            | List pantries for the volunteer directory, including subscription state and next shift preview |
| `POST`   | `/api/pantries/<id>/subscribe`       | Subscribe the current volunteer to new-shift emails for a pantry                  |
| `DELETE` | `/api/pantries/<id>/subscribe`       | Unsubscribe the current volunteer from pantry new-shift emails                    |
| `POST`   | `/api/pantries/<id>/shifts`          | Create a basic one-off shift                                                      |
| `POST`   | `/api/pantries/<id>/shifts/full-create` | Create a one-off or recurring shift series with roles in one request           |
| `PATCH`  | `/api/shifts/<id>`                   | Update simple shift details or reopen a cancelled shift                           |
| `PUT`    | `/api/shifts/<id>/full-update`       | Update one shift or a recurring future slice, including all roles, in one request |
| `DELETE` | `/api/shifts/<id>`                   | Cancel a shift                                                                    |
| `POST`   | `/api/shifts/<id>/cancel`            | Cancel one event or this-and-following recurring events                           |
| `POST`   | `/api/shift-roles/<id>/signup`       | Volunteer signs up for a shift role                                               |
| `PATCH`  | `/api/signups/<id>/reconfirm`        | Volunteer confirms/cancels after shift edits                                      |
| `PATCH`  | `/api/signups/<id>/attendance`       | Mark attendance (SHOW_UP / NO_SHOW)                                               |
| `GET`    | `/api/public/pantries/<slug>/shifts` | Public unauthenticated shift listing                                              |

### Authentication Flow
The app now shows an auth gate before the dashboard.

1. In `memory` mode, the user chooses a sample account and Flask creates a session.
2. In `firebase` mode, the browser authenticates with Google through Firebase and sends the Firebase ID token to Flask.
3. Flask verifies the token with the Firebase Admin SDK, links the local user by Firebase UID, falls back to email only for one-time legacy linking, and stores the local `user_id` in a session cookie.
4. The `My Account` tab lets users update `full_name`, `phone_number`, and saved timezone, start a verified email change, and delete their account.
5. Email changes require a fresh Google reauthentication in the browser, then Firebase sends a verification link to the new address.
6. Account deletion requires a fresh Google reauthentication, deletes the linked Firebase user, deletes the local user, and logs the user out.
7. The protected seeded `SUPER_ADMIN` account (`user_id = 1`) cannot delete itself.
8. Protected API routes read the authenticated user from the Flask session. Public routes remain under `/api/public/*`.

---

## User Roles & Features

### Super Admin
- Protected system role `SUPER_ADMIN` with `role_id = 0`.
- The seeded `user_id = 1` account is the single protected super admin.
- Counts as admin-capable everywhere the app checks admin access.
- Can remove `ADMIN` from other admin users.
- Cannot have its protected role edited through the app and cannot delete itself.

### Admin
- Full access to all pantries and shifts across the system.
- Can use the Admin page `Users` tab to search, monitor, and manage users.
- Can assign and remove pantry leads through search-based pantry and lead pickers in the Admin `Pantries` tab.
- Can assign `ADMIN` or `PANTRY_LEAD` to another user, but cannot remove `ADMIN` from another admin unless they are the super admin.
- Can change their own role and lose Admin access immediately if they demote themselves.

### Pantry Lead
- Can create, edit, and cancel shifts for pantries they are assigned to.
- Can create recurring weekly shift series with custom weekdays, weekly interval, and finite end rules.
- Can edit or cancel recurring shifts as either `This event only` or `This and following events`.
- Can use the search-based pantry picker in `Manage Shifts` and search shifts by name in `Shifts View`.
- Can filter the shared `Shifts View` table by `Incoming`, `Ongoing`, `Past`, and `Canceled`.
- Can view volunteer registrations and mark attendance.

### Volunteer
- Can browse open, non-expired shifts in the shared `Calendar` tab with pantry, search, and time-bucket filters plus month/week/day navigation.
- Can use the `Pantries` tab to search pantries by name/address, sort by name, and filter by `All`, `Subscribed`, or `Unsubscribed`.
- Can open a pantry detail view to see pantry leads and the next incoming shift preview.
- Can subscribe or unsubscribe from a pantry to receive email when that pantry creates a new one-off shift or recurring series.
- Each user has one system role in the runtime admin-management flow.
- Shift edits move existing signups to `PENDING_CONFIRMATION` with a 48-hour reservation window.
- Can reconfirm after shift edits.
- If they cancel during reconfirmation, the signup row is removed (same as normal cancel), so they can sign up again later if capacity is available.
- The `My Shifts` tab now defaults to a calendar view and can toggle back to the original list view.
- `My Shifts` calendar supports pantry/search/time-bucket filters, month/week/day navigation, responsive phone agenda rendering, and cancel/reconfirm actions from the shift detail modal.
- `My Shifts` list view supports volunteer-facing search and filters by pantry and time bucket while preserving the incoming/ongoing/past grouping.
- Can manage their own profile from `My Account`, including verified Firebase email changes and full account deletion.
- Sees shift times in the browser's local timezone and receives notification emails in the saved account timezone once it has been synced.
- Receives email notifications when Resend is configured

### Public (unauthenticated)
- Can view open shifts for any pantry via the public endpoint using a pantry slug (e.g., `/api/public/pantries/licking-county-pantry/shifts`).

---

## Quick Start

For detailed local setup instructions, including Docker configuration and database seeding, please refer to `SETUP.md`.

Set up Firebase Authentication and Resend email for the full experience, or use the in-memory options for quick testing without external dependencies. To set up Firebase Authentication, create a Firebase project, enable Google sign-in, and add the service account key to `backend/.env` as described in the `SETUP.md` Firebase section. Flask verifies Firebase ID tokens server-side and links them to local user accounts for session management.

If you want real email delivery in development or production, configure Resend in `backend/.env` with `RESEND_API_KEY` and `RESEND_FROM_EMAIL`. Resend’s official docs say sending uses a domain you own and recommend a subdomain such as `updates.yourdomain.com`; if your team does not already own a domain, register one first, then follow the Resend domain setup docs and DNS provider guide before using that sender address.

For this dev branch, the base schema in `backend/db/migrations/001_initial.sql` is the source of truth. If you already created a database from an older version of that file, recreate the dev schema so the current user/account changes, including `users.timezone`, pantry subscriptions, and recurring-shift tables/columns such as `shift_series`, `shifts.shift_series_id`, and `shifts.series_position`, apply cleanly.

### Running Tests

Install backend dependencies first:

```bash
cd backend
pip install -r requirements.txt
cd ..
```

Run the full suite from the repository root:

```bash
pytest tests
```

Run a specific test file:

```bash
pytest tests/test_signup_rate_limit.py
pytest tests/test_notifications.py
```

---

## Documentation structure
- `SETUP.md` — detailed local setup instructions, including Docker configuration, database seeding, Firebase Authentication setup, and Resend email configuration.
- `application_flow.md` — detailed documentation of the core application flows, including authentication, shift management, and notification logic.
- `data_model.md` — detailed documentation of the database schema and data model, including tables, relationships, and example records.
- `knowledge_transfer.md` — notes and documentation for future maintainers, including code structure, design decisions, and areas for future improvement.
- `MVP_FEATURES.md` — a list of core features that should be prioritized for the minimum viable product, with descriptions and acceptance criteria for each feature.

---

## Core Team

| Name         | Email                 |
| :----------- | :-------------------- |
| Jaweee Do    | do_g1@denison.edu     |
| Dong Tran    | tran_d2@denison.edu   |
| Jenny Nguyen | nguyen_j6@denison.edu |
| Khoa Ho      | ho_d1@denison.edu     |
| Hoang Ngo    | ngo_h2@denison.edu    |
