# Application Flow

A complete reference for how files, functions, and data communicate in the Volunteer Management System.

---

## 1. Repository File Map

```
volunteer_managing/
├── docker-compose.yml              # Spins up MySQL 8.4 container on port 3306
│
├── backend/
│   ├── app.py                      # Flask app: all routes, auth logic, business rules
│   ├── requirements.txt
│   ├── .env                        # Runtime config (DB credentials, backend type)
│   ├── notifications/
│   │   ├── __init__.py             # Notification package exports
│   │   └── notifications.py        # Resend email helpers for signup/update/cancellation/subscriber notifications + timezone-aware shift windows
│   │
│   ├── backends/
│   │   ├── base.py                 # Abstract interface: StoreBackend (ABC)
│   │   ├── factory.py              # Reads DATA_BACKEND env var, returns correct backend
│   │   ├── mysql_backend.py        # MySQLBackend: all SQL queries, row serialization
│   │   └── memory_backend.py       # MemoryBackend: in-memory dict store (no Docker needed)
│   │
│   ├── db/
│   │   ├── mysql.py                # Connection pool management (get_connection)
│   │   ├── init_schema.py          # Runs all SQL files in db/migrations idempotently on startup
│   │   ├── seed.py                 # Seeds MySQL from backend/data/mysql.json if empty
│   │   └── migrations/
│   │       └── 001_initial.sql     # CREATE TABLE statements for core schema (incl. users.timezone, pantry_subscriptions, and recurring shift series)
│   │
│   └── data/
│       ├── mysql.json              # MySQL seed data, including pantry subscriptions, recurring series, and a larger future mock shift set
│       └── in_memory.json          # In-memory backend seed data
│
└── frontend/
    ├── templates/
    │   └── dashboard.html          # Single HTML page — loaded by Flask's render_template()
    └── static/
        ├── css/
        │   └── dashboard.css
        └── js/
            ├── api-helpers.js      # Core fetch wrapper: apiGet/apiPost/apiPatch/apiPut/apiDelete
            ├── timezone-helpers.js # Browser timezone detection + shared local time formatting
            ├── user-functions.js   # getCurrentUser(), userHasRole(), createUser()
            ├── admin-functions.js  # getPantries(), createPantry(), addPantryLead()
            ├── lead-functions.js   # getShifts(), createFullShift(), updateShift(), updateFullShift(), cancelShiftWithScope(), markAttendance()
            ├── volunteer-functions.js  # signupForShift(), cancelSignup(), reconfirmSignup(), pantry subscription helpers
            └── dashboard.js        # App entry point: boot sequence, tab state, event handlers, volunteer pantry directory UI
```

---

## 2. Database Schema & Table Relationships

All tables are created from SQL files in [backend/db/migrations/](backend/db/migrations/) via `init_schema()` on every Flask startup (idempotent — uses `CREATE TABLE IF NOT EXISTS` for the schema baseline).

```
roles
─────
role_id (PK, INT)
role_name (UNIQUE)

users
─────
user_id (PK, AUTO_INCREMENT)
full_name
email (UNIQUE)
phone_number (nullable)
timezone (nullable)
auth_provider (nullable)
auth_uid (nullable, UNIQUE)
attendance_score (default 100)
created_at
updated_at

user_roles
──────────
PRIMARY KEY (user_id, role_id)
user_id (FK → users.user_id, ON DELETE CASCADE)
role_id (FK → roles.role_id, ON DELETE RESTRICT)
INDEX idx_user_roles_user_id (user_id)

pantries
────────
pantry_id (PK, AUTO_INCREMENT)
name
location_address
created_at
updated_at

pantry_leads
────────────
PRIMARY KEY (pantry_id, user_id)
pantry_id (FK → pantries.pantry_id, ON DELETE CASCADE)
user_id (FK → users.user_id, ON DELETE CASCADE)
INDEX idx_pantry_leads_user_id (user_id)

pantry_subscriptions
───────────────────
PRIMARY KEY (pantry_id, user_id)
pantry_id (FK → pantries.pantry_id, ON DELETE CASCADE)
user_id (FK → users.user_id, ON DELETE CASCADE)
created_at
INDEX idx_pantry_subscriptions_user_id (user_id)

shifts
──────
shift_id (PK, AUTO_INCREMENT)
pantry_id (FK → pantries.pantry_id, ON DELETE CASCADE)
shift_series_id (nullable FK → shift_series.shift_series_id, ON DELETE SET NULL)
series_position (nullable)
shift_name
start_time
end_time
status (default OPEN)
created_by (nullable FK → users.user_id, ON DELETE SET NULL)
created_at
updated_at
INDEX idx_shifts_pantry_id (pantry_id)
INDEX idx_shifts_shift_series_id (shift_series_id)

shift_series
────────────
shift_series_id (PK, AUTO_INCREMENT)
pantry_id (FK → pantries.pantry_id, ON DELETE CASCADE)
created_by (nullable FK → users.user_id, ON DELETE SET NULL)
timezone
frequency
interval_weeks
weekdays_csv
end_mode
occurrence_count (nullable)
until_date (nullable)
created_at
updated_at
INDEX idx_shift_series_pantry_id (pantry_id)

shift_roles
───────────
shift_role_id (PK, AUTO_INCREMENT)
shift_id (FK → shifts.shift_id, ON DELETE CASCADE)
role_title
required_count
filled_count (default 0)
status (default OPEN)
INDEX idx_shift_roles_shift_id (shift_id)

shift_signups
─────────────
signup_id (PK, AUTO_INCREMENT)
shift_role_id (FK → shift_roles.shift_role_id, ON DELETE CASCADE)
user_id (FK → users.user_id, ON DELETE CASCADE)
signup_status (default CONFIRMED)
reservation_expires_at (nullable)
created_at
UNIQUE KEY uq_shift_signups_role_user (shift_role_id, user_id)
INDEX idx_shift_signups_shift_role_id (shift_role_id)
INDEX idx_shift_signups_user_id (user_id)
INDEX idx_shift_signups_role_status_reservation (shift_role_id, signup_status, reservation_expires_at)
```

Relationship summary:

- Deleting a pantry cascades to its shifts, then to shift roles, then to shift signups.
- Recurring schedules live in `shift_series`, while each actual occurrence still lives as a normal row in `shifts`.
- `shifts.shift_series_id` links each occurrence back to its series and `series_position` preserves order inside the recurring slice.
- Deleting a user cascades out of `user_roles`, `pantry_leads`, and `shift_signups`.
- Deleting a pantry or user also cascades through `pantry_subscriptions`.
- Deleting a user does not block on shifts they created because `shifts.created_by` uses `ON DELETE SET NULL`.
- Role rows in `roles` cannot be deleted while referenced from `user_roles` because that foreign key uses `ON DELETE RESTRICT`.
- Duplicate signup to the same role is blocked by `uq_shift_signups_role_user (shift_role_id, user_id)`.
- Duplicate pantry subscription is blocked by the composite primary key `(pantry_id, user_id)`.
- Reservation-aware capacity checks are supported by `idx_shift_signups_role_status_reservation`.

---

## 3. Backend Module Chain

### Startup sequence (once, when `python app.py` runs)

```
app.py
  load_dotenv("backend/.env")           ← reads DATA_BACKEND, MYSQL_*, RESEND_* vars
  create_backend()   [factory.py]
    │  DATA_BACKEND == "mysql"?
    ├─ YES →
    │    init_schema()  [db/init_schema.py]
    │      ensure_database_exists()      ← connects without DB name, CREATE DATABASE IF NOT EXISTS
    │      apply_sql(*.sql in migrations/)   ← CREATE TABLE IF NOT EXISTS baseline schema
    │    MySQLBackend()  [mysql_backend.py]
    │    backend.is_empty()?
    │      YES → seed_mysql_from_json("data/mysql.json")
    │    return MySQLBackend instance
    └─ NO  → return MemoryBackend instance
  backend = <chosen instance>            ← module-level singleton used by all routes
  notifications.send_*()               ← called for confirmed signups, shift updates, shift cancellations, and pantry-subscriber new-shift emails
  app.run(port=5000)
```

### Connection pool (`db/mysql.py`)

`get_pool()` creates a single `MySQLConnectionPool` (size=5 by default) the first time it is called. Every subsequent call returns the same pool. All database operations use the `get_connection()` context manager:

```python
@contextmanager
def get_connection() -> Iterator[MySQLConnection]:
    conn = get_pool().get_connection()   # borrows a connection from the pool
    try:
        yield conn                       # caller runs queries here
    finally:
        conn.close()                     # returns connection to pool (does NOT close it)
```

`autocommit=False` — every write operation in `mysql_backend.py` explicitly calls `conn.commit()`.

### The StoreBackend abstraction (`backends/base.py`)

`base.py` defines `StoreBackend` as an abstract base class (Python ABC) with 25+ `@abstractmethod` signatures. `app.py` only ever calls methods on this interface — it has zero imports from `mysql_backend.py` or `memory_backend.py` directly. This means swapping the backend (e.g. for testing) requires changing only the `DATA_BACKEND` env var.

```
app.py calls:        backend.create_shift(...)
                              │
                    StoreBackend (base.py)    ← interface only, no logic
                              │
              ┌───────────────┴───────────────┐
        MySQLBackend                    MemoryBackend
        (mysql_backend.py)              (memory_backend.py)
        runs SQL INSERT                 appends to Python dict
```

### Notification service (`notifications/notifications.py`)

The notification module is intentionally separate from Flask route handlers:

- Loads `RESEND_API_KEY` and `RESEND_FROM_EMAIL` from `backend/.env`
- Normalizes shift/pantry/user data into an email payload
- Resolves the recipient timezone from `users.timezone`, falling back to `America/New_York`
- Sends the email through Resend for:
  - confirmed signups
  - shift updates that require reconfirmation
  - shift cancellations
- Returns a structured result dict with:
  - `ok`
  - `code`
  - `message`
  - `recipient_email`
  - `subject`
  - `provider_response`

`app.py` consumes that result in dedicated route helpers and logs warning details when delivery is skipped or fails.

### Recurring shift flow (`app.py`)

Recurring shifts are stored as concrete shift rows linked by a shared `shift_series` record, so volunteer signup, capacity, notifications, calendar rendering, and attendance still operate on normal shift/role/signup rows.

- `normalize_recurrence_payload(...)`
  - validates weekly recurrence input from the manager UI
  - supports custom weekdays, weekly interval, and finite end rules (`COUNT` or `UNTIL`)
- `generate_weekly_occurrences(...)`
  - builds concrete occurrences in the series timezone first, then converts them to UTC
  - prevents DST drift across recurring weekly shifts
- `POST /api/pantries/<id>/shifts/full-create`
  - creates one one-off shift when `recurrence` is omitted
  - creates one `shift_series` row plus many concrete `shifts` and `shift_roles` rows when `recurrence` is present
- `PUT /api/shifts/<id>/full-update`
  - `apply_scope: "single"` updates one occurrence
  - `apply_scope: "future"` updates the clicked occurrence and later occurrences in the recurring slice
- `POST /api/shifts/<id>/cancel`
  - `apply_scope: "single"` cancels one occurrence
  - `apply_scope: "future"` cancels the clicked occurrence and later occurrences

---

## 4. Data Serialization Path

Every value that comes out of MySQL is a raw Python dict with raw types (datetime objects, integers, etc.). Before it can be sent to the browser as JSON, it must be serialized. Here is the full chain for a shift:

```
MySQL row (cursor.fetchone())
  → raw dict: { "shift_id": 1, "start_time": datetime(2025,6,1,9,0), ... }

mysql_backend.py: _serialize_shift(row)
  → clean dict: { "shift_id": 1, "shift_series_id": 3, "series_position": 2, "start_time": "2025-06-01T09:00:00Z", ... }
     (datetimes converted to ISO-8601 strings by _to_iso_z())

app.py: route handler attaches related data
  → enriched dict: { ..., "is_recurring": true/false, "recurrence": {...}, "roles": [ {shift_role_id, role_title, ...}, ... ] }

app.py: jsonify(shift)
  → Flask serializes dict to JSON string, sets Content-Type: application/json

Browser: fetch() resolves → response.json()
  → JavaScript object: { shift_id: 1, start_time: "2025-06-01T09:00:00Z", roles: [...] }

timezone-helpers.js:
  getBrowserTimeZone()                        ← Intl.DateTimeFormat().resolvedOptions().timeZone
  formatLocalDateTime(...) / formatLocalTimeRange(...)

lead-functions.js / volunteer-functions.js:
  formatDateTimeForDisplay(shift.start_time)  ← timezone-helpers.js → browser-local string
  classifyShiftBucket(shift)                  ← compares start/end to new Date()
  getCapacityStatus(role)                     ← filled_count vs required_count → 'full'|'almost-full'|'available'
```

---

## 5. Frontend File Load Order & Dependencies

`dashboard.html` loads all JS files as plain `<script>` tags at the bottom of `<body>` ([dashboard.html:343-348](frontend/templates/dashboard.html#L343)):

```html
<script src=".../api-helpers.js"></script>       ← 1st: loaded first, no dependencies
<script src=".../user-functions.js"></script>    ← 2nd: calls apiGet() from api-helpers
<script src=".../admin-functions.js"></script>   ← 3rd: calls apiGet/apiPost from api-helpers
<script src=".../lead-functions.js"></script>    ← 4th: calls apiGet/apiPost from api-helpers
<script src=".../volunteer-functions.js"></script> ← 5th: calls apiGet/apiPost from api-helpers
<script src=".../dashboard.js"></script>         ← 6th: calls functions from ALL 4 above
```

All functions are in the global `window` scope (no modules/imports). `dashboard.js` guards against load-order failures at line 15:

```javascript
if (typeof getCurrentUser === 'undefined') {
    throw new Error('Required functions not loaded. Please refresh the page.');
}
```

**Who calls what across files:**

```
dashboard.js  →  user-functions.js:     getCurrentUser(), userHasRole()
dashboard.js  →  admin-functions.js:    getPantries(), createPantry(), addPantryLead(), removePantryLead()
dashboard.js  →  lead-functions.js:     getShifts(), getActiveShifts(), createFullShift(), updateShift(),
                                        updateFullShift(), cancelShiftWithScope(), deleteShift(),
                                        createShiftRole(), updateShiftRole(), deleteShiftRole(),
                                        getShiftRegistrations(), markAttendance()
dashboard.js  →  volunteer-functions.js: signupForShift(), cancelSignup(), reconfirmSignup(),
                                         getUserSignups(), classifyShiftBucket(), formatShiftDate(),
                                         formatShiftTime(), getCapacityStatus()

All 4 function files  →  api-helpers.js:  apiGet(), apiPost(), apiPatch(), apiDelete()
api-helpers.js        →  browser fetch()
```

---

## 6. Frontend Boot Sequence

When the browser finishes loading the page, `dashboard.js` fires `window.addEventListener('load', ...)` ([dashboard.js:12](frontend/static/js/dashboard.js#L12)). The full initialization sequence:

```
window 'load' event fires
  │
  ├─ 1. getCurrentUser()          [user-functions.js]
  │       apiGet('/api/me')        [api-helpers.js → fetch]
  │       ← { user_id, email, roles: ["ADMIN" | "SUPER_ADMIN" | ...], timezone }
  │       sets module-level: currentUser
  │       writes email/roles to #user-email, #user-role in DOM
  │
  ├─ 2. syncCurrentUserTimezoneIfNeeded() [dashboard.js]
  │       getBrowserTimeZone()     [timezone-helpers.js]
  │       compare browser timezone vs currentUser.timezone
  │       if missing or changed → PATCH /api/me { timezone }
  │       updates module-level currentUser
  │
  ├─ 3. setupRoleBasedUI()        [dashboard.js:60]
  │       reads currentUser.roles
  │       shows/hides nav tabs:
  │         VOLUNTEER  → shows "My Shifts" tab
  │         PANTRY_LEAD or admin-capable → shows "Manage Shifts" tab
  │         ADMIN or SUPER_ADMIN → shows "Admin Panel" tab
  │       returns the default tab name to activate
  │
  ├─ 4. loadPantries()            [dashboard.js:121]
  │       getAllPantries()         [admin-functions.js]
  │         apiGet('/api/all_pantries')
  │         ← [ {pantry_id, name, ...}, ... ]
  │       sets module-level: allPublicPantries
  │       syncs the shared Manage Shifts pantry search picker
  │         #pantry-select-search + hidden #pantry-select
  │       syncs the Admin pantry assignment search picker
  │         #assign-pantry-search + hidden #assign-pantry
  │
  ├─ 5. setupEventListeners()     [dashboard.js:1152]
  │       attaches click handlers to nav tabs → activateTab()
  │       attaches click handlers to Admin subtabs → setAdminSubtab() + loadAdminTab()
  │       attaches submit to #create-shift-form → createFullShift()
  │       attaches recurring-shift UI handlers:
  │         #shift-repeat-toggle
  │         weekday chips
  │         finite end controls
  │       attaches recurring edit/cancel scope modal handlers
  │       attaches submit to #create-pantry-form → createPantry()
  │       attaches click to #assign-lead-btn → addPantryLead()
  │       attaches search/result handlers for:
  │         #pantry-select-search
  │         #assign-pantry-search
  │         #assign-lead-search
  │       attaches Manage Shifts search + status filter handlers
  │       attaches Admin Users search/filter/profile/role-save handlers
  │
  └─ 6. activateTab(defaultTab)   [dashboard.js:91]
          shows the target tab's content div
          calls the appropriate loader:
            'calendar'   → loadCalendarShifts()
            'my-shifts'  → loadMyRegisteredShifts()
            'shifts'     → loadShiftsTable()
            'admin'      → loadAdminTab()
```

---

## 7. Request Lifecycle (Every API Call)

Every single API request from the browser follows this exact path:

```
dashboard.js calls a domain function
  e.g. createFullShift(pantryId, data)
        │
        ▼
lead-functions.js: createFullShift()
  apiPost(`/api/pantries/${pantryId}/shifts/full-create`, data)
        │
        ▼
api-helpers.js: apiCall(path, options)
  reads window.location.search               ← preserves ?user_id=X
  fullPath = '/api/pantries/1/shifts/full-create?user_id=4'
  fetch(fullPath, { method:'POST', body: JSON.stringify(data) })
        │
        ▼  HTTP POST over localhost
        │
app.py: Flask router matches route
        │
        ▼
@app.before_request: set_current_user()      ← runs before EVERY route
  request.args.get("user_id") or DEFAULT_USER_ID (4)
  g.current_user_id = 4                      ← stored in Flask's per-request context
        │
        ▼
Route handler: create_shift(pantry_id=1)
  current_user()
    find_user_by_id(g.current_user_id)
      backend.get_user_by_id(4)             ← MySQLBackend: SELECT * FROM users WHERE user_id=4
  is_admin_capable(4)
    backend.get_user_roles(4)               ← SELECT role_name FROM roles JOIN user_roles ...
  validate payload fields
  backend.create_shift(pantry_id, ...)      ← MySQLBackend
        │
        ▼
mysql_backend.py: create_shift()
  with get_connection() as conn:            ← borrows from pool
    cursor.execute("INSERT INTO shifts ...")
    conn.commit()
    if recurrence omitted:
      create one shift row + related role rows
    else:
      create one shift_series row + many concrete shift rows + role clones
  return JSON summary                        ← created_shift_count, first_shift, shift_series_id
        │
        ▼  back in app.py
return jsonify(summary), 201                ← Flask serializes to JSON, HTTP 201
        │
        ▼  HTTP 201 JSON response
        │
api-helpers.js: apiCall()
  response.ok == true
  return response.json()                    ← parsed JS object
        │
        ▼
lead-functions.js: createFullShift() returns summary
        │
        ▼
dashboard.js: receives creation summary
  DOM update — refreshes manager table + calendar
  (no page reload)
```

---

## 8. Authentication Lifecycle

### Current State: Session + Firebase Google Auth

The app now has a real authentication gate:

```
Browser
  auth.js: bootstrapAuthShell()
    GET /api/auth/config
    GET /api/me
      └─ if 401 → stay on auth gate
      └─ if 200 → enter dashboard

Firebase mode:
  Browser opens Google popup
  firebase.auth().signInWithPopup(GoogleAuthProvider)
  Browser gets Firebase ID token
  POST /api/auth/login/google

Flask app.py:
  verify_google_token(id_token)
  lookup local user by auth_uid first
  fallback to email only for one-time legacy linking
  sync verified Firebase email if it changed
  store local user_id in Flask session cookie

Protected route requests:
  browser sends Flask session cookie
  @app.before_request loads session["user_id"] into g.current_user_id
  route handlers use the local session-backed user
```

`/api/me` now powers the `My Account` tab. It returns current profile fields, roles, saved timezone, attendance score, auth metadata, and timestamps.

Timezone persistence flow:

```
Browser loads dashboard
  timezone-helpers.js
    Intl.DateTimeFormat().resolvedOptions().timeZone
  dashboard.js
    getCurrentUser() → /api/me
    compare browser timezone with currentUser.timezone
    if different:
      PATCH /api/me { timezone: "America/Chicago" }
    My Account note shows:
      browser timezone for web rendering
      saved timezone for emails

Google signup flow
  auth.js
    POST /api/auth/signup/google
      {
        id_token,
        full_name,
        phone_number,
        timezone
      }

Email notifications
  notifications.py
    ZoneInfo(saved_user_timezone or "America/New_York")
    localized email shift window
```

Sensitive account actions:

```
Email change
  My Account tab
    POST /api/me/email-change/prepare
    force fresh Google popup reauthentication
    firebase User.verifyBeforeUpdateEmail(new_email)
    user clicks verification link
    next successful Google login syncs the verified email into the local account by auth_uid

Account deletion
  My Account tab
    force fresh Google popup reauthentication
    get fresh Firebase ID token
    DELETE /api/me { id_token }

Flask app.py:
  verify_google_token(id_token)
  confirm Firebase uid matches current local auth_uid
  firebase_admin.auth.delete_user(uid)
  backend.delete_user(user_id)
  clear Flask session

Protected rule:
  seeded user_id = 1 with SUPER_ADMIN
  cannot delete itself
```

The Admin `Users` subtab is driven by the following flow:

```
Admin Users subtab
  GET /api/users?q=<text>&role=<role>
    └─ returns serialized users with roles for the table
  click a user
    GET /api/users/<user_id>
      └─ returns the full profile payload for the side panel
  choose one role button
    PATCH /api/users/<user_id>/roles { role_ids: [<single_role_id>] }
      ├─ enforces one editable role per user
      ├─ blocks SUPER_ADMIN assignment/removal
      ├─ blocks normal admins from removing another admin's ADMIN role
      └─ refreshes the current session if the actor edits themself
```

---

## 9. Error Handling Flow

### Backend → Frontend

Every error from Flask is a consistent JSON shape:

```python
return jsonify({"error": "Human-readable message"}), <status_code>
# Special conflict case:
return jsonify({"error": "Past shifts are locked", "code": "PAST_SHIFT_LOCKED"}), 409
```

| Code | Meaning | Common trigger |
|---|---|---|
| 400 | Validation failure | Missing field, duplicate signup, shift already ended |
| 403 | Forbidden | User lacks required role, not a lead for this pantry |
| 404 | Not found | Invalid ID in URL |
| 409 | Conflict | Role full on reconfirm, reservation expired, or past shift is locked |

### Frontend error handling chain

```
api-helpers.js: apiCall()
  if (!response.ok)
    errorText = await response.text()       ← raw JSON string e.g. '{"error":"Forbidden"}'
    throw new Error(`API Error: 403 - ...`) ← becomes a JS Error object

lead-functions.js / volunteer-functions.js: every function has try/catch
  catch (error) {
    console.error('Failed to create shift:', error)
    throw error                              ← re-throws up to dashboard.js
  }

dashboard.js: call site catch block
  showMessage('shifts', `Failed: ${error.message}`, 'error')
  ← writes to the relevant #message-<tab> div in the DOM

Special cases for reconfirm:
1. `409 ROLE_FULL_OR_UNAVAILABLE` when reduced capacity no longer has room.
2. `409 RESERVATION_EXPIRED` when the 48-hour reservation window passed.
  catch (error) {
    if error contains "ROLE_FULL_OR_UNAVAILABLE":
      showMessage('my-shifts', 'This role is full or unavailable...', 'error')
    else if error contains "RESERVATION_EXPIRED":
      showMessage('my-shifts', 'Your reservation expired. Please sign up again if slots are available.', 'error')
    else:
      showMessage('my-shifts', `Action failed: ${error.message}`, 'error')
  }
```
