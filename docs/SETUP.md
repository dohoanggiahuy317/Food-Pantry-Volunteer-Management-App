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
DATA_BACKEND=mysql

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=volunteer_managing
MYSQL_USER=volunteer_user
MYSQL_PASSWORD=volunteer_pass

MYSQL_POOL_SIZE=5
MYSQL_CONNECT_TIMEOUT=10

SEED_MYSQL_FROM_JSON_ON_EMPTY=true
```

**Variable reference:**

| Variable | Purpose |
|---|---|
| `DATA_BACKEND` | Set to `mysql` for the real DB, or `memory` for an in-memory backend (no Docker needed — useful for quick testing) |
| `MYSQL_HOST` / `MYSQL_PORT` | Where Flask looks for MySQL. Docker maps the container to `localhost:3306` |
| `MYSQL_DATABASE` | The database name created by Docker on first start |
| `MYSQL_USER` / `MYSQL_PASSWORD` | Credentials defined in `docker-compose.yml` |
| `SEED_MYSQL_FROM_JSON_ON_EMPTY` | When `true`, Flask auto-populates the DB from `backend/data/db.json` if the tables are empty |

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

> **First startup note:** Flask will automatically initialize the database schema (create all tables) and seed sample data from `backend/data/db.json` if the database is empty. You should see this happen in the terminal output. No manual SQL migrations are required.

---

## Step 4: Accessing the App & Mock Authentication

> **Note:** Real authentication has not yet been implemented. Steps 1–3 above are fully functional. This section describes the temporary dev-mode workaround in use until Firebase Auth is integrated (see [Upcoming: Firebase Authentication](#upcoming-firebase-authentication) below).

**Open the app in your browser:**

```
http://localhost:5000
```

Flask serves the full application — both the frontend (HTML/CSS/JS) and the API — from this single address. There is no separate frontend server to run.

**How mock authentication works:**

The app defaults to acting as **user ID 4 (Admin)**. To switch users, append a `?user_id=` query parameter to any URL:

| URL | Who you are acting as |
|---|---|
| `http://localhost:5000` | Default: Admin (user_id = 4) |
| `http://localhost:5000/?user_id=1` | Acts as user with ID 1 |
| `http://localhost:5000/?user_id=2` | Acts as user with ID 2 |

To find available user IDs and their roles, query the API directly:

```
http://localhost:5000/api/users
```

---

## Upcoming: Firebase Authentication

> **Status: Not yet active.** This section documents the planned Firebase Auth integration. Until it is complete, follow Step 4 above for dev access.

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
- The above variables will be added to `env.example` once the integration is merged.
- Do **not** commit `serviceAccountKey.json` to version control — it is a secret.

Once these steps are complete, the mock `?user_id=` system will be removed and the app will require a real login.
