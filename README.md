# Volunteer Management System

A web application for managing volunteer shifts at food pantries. Pantry leads and admins create and manage shifts; volunteers and the public can browse open shifts by pantry.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Frontend | Vanilla JS, HTML, CSS (served directly via Flask templates, no build tools required) |
| Database | MySQL 8.4 (containerized via Docker) |
| Auth | Configurable auth provider: in-memory demo auth or Firebase Authentication with Google sign-in. Flask uses session cookies after login. |

---

## Architecture & API Design

### Backend Factory Pattern

The data layer uses an abstract `StoreBackend` interface with two concrete implementations:

- **`MySQLBackend`** — production backend; connects to the MySQL Docker container.
- **`MemoryBackend`** — in-memory backend backed by plain Python dicts; no database required. Useful for isolated testing.

The active backend is selected at startup via the `DATA_BACKEND` environment variable (defaults to `mysql`). Swapping backends requires no changes to `app.py`.

### Auth Provider Switch

Authentication is configured separately from data storage:

- **`AUTH_PROVIDER=memory`** — sample accounts for local login/logout testing.
- **`AUTH_PROVIDER=firebase`** — Google sign-in with Firebase Authentication, verified server-side through the Firebase Admin SDK.

After a successful login or signup, Flask stores the authenticated local user in a session cookie and all protected API routes use that session.

### Core API Routes

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/auth/config` | Get active auth mode and safe browser config |
| `POST` | `/api/auth/login/google` | Log in an existing local user with Google/Firebase |
| `POST` | `/api/auth/signup/google` | Create a volunteer account after Google auth |
| `POST` | `/api/auth/login/memory` | Log in with a sample in-memory account |
| `POST` | `/api/auth/logout` | Clear the current session |
| `GET` | `/api/me` | Get current user with roles |
| `GET` | `/api/pantries` | List pantries accessible to current user |
| `GET` | `/api/pantries/<id>/shifts` | List all shifts for a pantry (admin/lead view) |
| `GET` | `/api/pantries/<id>/active-shifts` | List non-expired shifts (public/volunteer view) |
| `POST` | `/api/pantries/<id>/shifts` | Create a new shift |
| `PATCH` | `/api/shifts/<id>` | Update shift details |
| `DELETE` | `/api/shifts/<id>` | Cancel a shift |
| `POST` | `/api/shift-roles/<id>/signup` | Volunteer signs up for a shift role |
| `PATCH` | `/api/signups/<id>/reconfirm` | Volunteer confirms/cancels after shift edits |
| `PATCH` | `/api/signups/<id>/attendance` | Mark attendance (SHOW_UP / NO_SHOW) |
| `GET` | `/api/public/pantries/<slug>/shifts` | Public unauthenticated shift listing |

### Authentication Flow
The app now shows an auth gate before the dashboard.

1. In `memory` mode, the user chooses a sample account and Flask creates a session.
2. In `firebase` mode, the browser authenticates with Google through Firebase and sends the Firebase ID token to Flask.
3. Flask verifies the token with the Firebase Admin SDK, links or creates the local user, and stores the local `user_id` in a session cookie.
4. Protected API routes read the authenticated user from the Flask session. Public routes remain under `/api/public/*`.

---

## User Roles & Features

### Admin
- Full access to all pantries and shifts across the system.
- Can create and manage users, assign pantry leads, and cancel any shift.

### Pantry Lead
- Can create, edit, and cancel shifts for pantries they are assigned to.
- Can view volunteer registrations and mark attendance.

### Volunteer
- Can browse open, non-expired shifts.
- Shift edits move existing signups to `PENDING_CONFIRMATION` with a 48-hour reservation window.
- Can reconfirm after shift edits.
- If they cancel during reconfirmation, the signup row is removed (same as normal cancel), so they can sign up again later if capacity is available.

### Public (unauthenticated)
- Can view open shifts for any pantry via the public endpoint using a pantry slug (e.g., `/api/public/pantries/licking-county-pantry/shifts`).

---

## Quick Start

For detailed local setup instructions, including Docker configuration and database seeding, please refer to `SETUP.md`.

---

## Core Team

| Name | Email |
|---|---|
| Jaweee Do | do_g1@denison.edu |
| Dong Tran | tran_d2@denison.edu |
| Jenny Nguyen | nguyen_j6@denison.edu |
| Khoa Ho | ho_d1@denison.edu |
| Hoang Ngo | ngo_h2@denison.edu |

Big shout-out to Dr. Goldweber for your support! 🍻
