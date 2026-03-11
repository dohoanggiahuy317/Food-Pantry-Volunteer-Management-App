# Volunteer Management System

A web application for managing volunteer shifts at food pantries. Pantry leads and admins create and manage shifts; volunteers and the public can browse open shifts by pantry.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Frontend | Vanilla JS, HTML, CSS (served directly via Flask templates, no build tools required) |
| Database | MySQL 8.4 (containerized via Docker) |
| Auth | Firebase Authentication. Frontend handles secure login; Flask backend verifies Firebase JWT tokens via the Admin SDK. |

---

## Architecture & API Design

### Backend Factory Pattern

The data layer uses an abstract `StoreBackend` interface with two concrete implementations:

- **`MySQLBackend`** — production backend; connects to the MySQL Docker container.
- **`MemoryBackend`** — in-memory backend backed by plain Python dicts; no database required. Useful for isolated testing.

The active backend is selected at startup via the `DATA_BACKEND` environment variable (defaults to `mysql`). Swapping backends requires no changes to `app.py`.

### Core API Routes

| Method | Route | Description |
|---|---|---|
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
The system uses Firebase Authentication for identity management. 
1. The Vanilla JS frontend authenticates users directly with Firebase.
2. The frontend retrieves a secure JWT (ID Token) from Firebase.
3. API requests to protected Flask routes must include this token in the header (`Authorization: Bearer <TOKEN>`).
4. The Flask backend uses the Firebase Admin SDK to verify the token and identify the user before processing the request.

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
