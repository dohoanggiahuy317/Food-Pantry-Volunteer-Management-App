# Setup Guide

## Prerequisites

Make sure the following tools are installed before you begin:

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **Docker** — [docs.docker.com/get-docker](https://docs.docker.com/get-docker/)
- **Docker Compose** — included with Docker Desktop; verify with `docker compose version`

---

## Step 1: Database Setup (Docker)

The application uses MySQL 8.4 running inside a Docker container. From the **repository root**, run:

```bash
docker compose up -d mysql
```

This pulls the MySQL image (first run only), creates the `volunteer_managing` database, and starts the container in the background. Your data is persisted in a named Docker volume (`mysql_data`), so it survives container restarts.

**To stop the database when you're done working:**

```bash
docker compose down
```

> Note: `docker compose down` stops and removes the container but preserves the data volume. To also wipe the data, run `docker compose down -v`.

---

## Step 2: Environment Variables

Inside the `backend/` folder, copy the example env file and leave the values as-is — they match the credentials defined in `docker-compose.yml` exactly.

```bash
cp backend/env.example backend/.env
```

Your `backend/.env` should look like this:

```env
AUTH_PROVIDER=firebase
FIREBASE_API_KEY=
FIREBASE_AUTH_DOMAIN=
FIREBASE_PROJECT_ID=
FIREBASE_APP_ID=
FIREBASE_ADMIN_CREDENTIALS=backend/firebase_private_key.json

FLASK_SECRET_KEY=huybeo

DATA_BACKEND=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=volunteer_managing
MYSQL_USER=volunteer_user
MYSQL_PASSWORD=volunteer_pass
MYSQL_POOL_SIZE=5
MYSQL_CONNECT_TIMEOUT=10
SEED_MYSQL_FROM_JSON_ON_EMPTY=true

RESEND_API_KEY=
RESEND_FROM_EMAIL=noreply@updates.example.com
```

**Variable reference:**

| Variable                        | Purpose                                                                                        |
| :------------------------------ | :--------------------------------------------------------------------------------------------- |
| `AUTH_PROVIDER`                 | `memory` for sample login/logout, or `firebase` for Google sign-in with Firebase               |
| `DATA_BACKEND`                  | Set to `mysql` for the real DB, or `memory` for an in-memory backend                           |
| `FLASK_SECRET_KEY`              | Secret used to sign Flask session cookies                                                      |
| `MYSQL_HOST` / `MYSQL_PORT`     | Where Flask looks for MySQL. Docker maps the container to `localhost:3306`                     |
| `MYSQL_DATABASE`                | The database name created by Docker on first start                                             |
| `MYSQL_USER` / `MYSQL_PASSWORD` | Credentials defined in `docker-compose.yml`                                                    |
| `SEED_MYSQL_FROM_JSON_ON_EMPTY` | When `true`, Flask auto-populates the DB from `backend/data/mysql.json` if the tables are empty |
| `RESEND_API_KEY`                | API key used by `backend/notifications/notifications.py` to send volunteer notification emails |
| `RESEND_FROM_EMAIL`             | Verified sender address used for outgoing email (for example `noreply@updates.example.com`)    |

---

## Step 3: Running the Application

All commands below are run from the **repository root**.

**1. Navigate to the backend directory:**

```bash
cd backend
```

**2. Create and activate a Python virtual environment** (recommended — keeps dependencies isolated from your system Python):

```bash
# Create the virtual environment
python3 -m venv .venv

# Activate it — macOS / Linux
source .venv/bin/activate

# Activate it — Windows
.venv\Scripts\activate
```

You'll know it's active when your terminal prompt shows `(.venv)`.

**3. Install dependencies:**

```bash
pip install -r requirements.txt
```

**4. Start the Flask server:**

```bash
python app.py
```

> **First startup note:** Flask will automatically initialize the database schema (create all tables from `backend/db/migrations/001_initial.sql`) and seed sample data from `backend/data/mysql.json` if the database is empty.  
> For dev, if you already have an older schema and pull schema changes, recreate/reset your local MySQL data volume so the new baseline schema is applied cleanly. The current baseline includes `users.timezone` for localized emails, `pantry_subscriptions` for volunteer pantry notifications, and recurring-shift support through `shift_series`, `shifts.shift_series_id`, and `shifts.series_position`.
> The current MySQL seed includes a larger future shift dataset so the calendar and signup flows have much denser mock data out of the box.

---

## Running Tests

Install the backend dependencies first if you have not already:

```bash
cd backend
pip install -r requirements.txt
cd ..
```

Run tests from the repository root so `pytest` discovers the repository-level `tests/` directory:

```bash
pytest tests
```

Run an individual file when you only want a focused check:

```bash
pytest tests/test_signup_rate_limit.py
pytest tests/test_notifications.py
```

---

## Step 4: Accessing the App & Mock Authentication

**Open the app in your browser:**

```
http://localhost:5000
```

Flask serves the full application — both the frontend (HTML/CSS/JS) and the API — from this single address. There is no separate frontend server to run.

**How authentication works now:**

- If `AUTH_PROVIDER=memory`, the first screen shows sample demo accounts for login/logout testing.
- If `AUTH_PROVIDER=firebase`, the first screen shows Google login/signup and the app requires the Firebase variables described below.

---

## Step 5: Optional Resend Email Setup

Volunteer notification emails are sent through `backend/notifications/notifications.py` for confirmed signups, shift updates that require reconfirmation, shift cancellations, and pantry subscriber notifications when a pantry posts a new shift or recurring series.

Timezone behavior in the current app:

- API timestamps remain stored and transported as UTC ISO strings.
- The browser detects a user's timezone with `Intl.DateTimeFormat().resolvedOptions().timeZone`.
- After login, the frontend syncs that timezone to the user profile through `PATCH /api/me` if it is missing or changed.
- Google signup includes the browser timezone in the initial signup request.
- Notification emails render shift times in the saved user timezone, with `America/New_York` as the fallback when none is stored or the value is invalid.

**1. Make sure you control a sending domain**

- Resend requires a domain you own and recommends using a subdomain such as `updates.yourdomain.com`.
- If your team does not already own a domain, register one first with your preferred registrar.

**2. Add the domain in Resend**

- Create or log in to your Resend account.
- Add the domain or subdomain you want to send from.
- Official doc: [Managing Domains](https://resend.com/docs/dashboard/domains/introduction)

**3. Verify DNS records with your DNS provider**

- Copy the SPF and DKIM records shown by Resend into your DNS provider.
- Resend’s domain docs describe the verification flow and the official DNS provider guides show the exact steps for providers such as Cloudflare, GoDaddy, Namecheap, Route 53, and others.
- After adding the records, trigger verification in Resend and wait until the domain status is `verified`.
- Official DNS guide index: [Resend DNS Guides](https://resend.com/docs/knowledge-base/introduction)

**4. Create a sending API key**

- In the Resend dashboard, create an API key with `Sending access` or `Full access`.
- Paste that value into `RESEND_API_KEY` in `backend/.env`.
- Official doc: [Resend API Keys](https://resend.com/docs/dashboard/api-keys/introduction)

**5. Configure the sender address**

- Set `RESEND_FROM_EMAIL` to a verified sender on your Resend domain, for example `noreply@updates.example.com`.
- Restart Flask after changing env values.

**Behavior in this repo**

- If `RESEND_API_KEY` or `RESEND_FROM_EMAIL` is missing, the notification helper returns a structured failure result and `app.py` logs a warning instead of crashing the signup or shift-management flow.
- If Resend is configured correctly, volunteers receive emails for confirmed signups, shift updates that require reconfirmation, and shift cancellations.
- Those emails use the saved `users.timezone` value when formatting the shift time window.

---

## Firebase Authentication

When Firebase Auth is integrated, the following will be required:

**1. Create a Firebase project**
- Go to [console.firebase.google.com](https://console.firebase.google.com) and create a new project.
- Under **Authentication → Sign-in method**, enable your chosen providers (e.g. Email/Password, Google).

**2. Obtain your Firebase config**
- In the Firebase console go to **Project Settings → General → Your apps**.
- Register a Web app and copy the config object. You will need these values:

```env
FIREBASE_API_KEY=
FIREBASE_AUTH_DOMAIN=
FIREBASE_PROJECT_ID=
FIREBASE_APP_ID=
```

**3. Obtain a Firebase Admin SDK service account (backend)**
- In the Firebase console go to **Project Settings → Service accounts**.
- Click **Generate new private key** and download the JSON file.
- Add the path (or its contents) to your `backend/.env`:

```env
FIREBASE_ADMIN_CREDENTIALS=path/to/serviceAccountKey.json
```

**4. Add all Firebase variables to `backend/.env`**
- Set `AUTH_PROVIDER=firebase` and add:

```env
FIREBASE_API_KEY=
FIREBASE_AUTH_DOMAIN=
FIREBASE_PROJECT_ID=
FIREBASE_APP_ID=
FIREBASE_ADMIN_CREDENTIALS=path/to/serviceAccountKey.json
```

- Do **not** commit `serviceAccountKey.json` to version control — it is a secret.

Once these steps are complete, the app will use the pre-dashboard auth gate instead of the old mock `?user_id=` flow.
