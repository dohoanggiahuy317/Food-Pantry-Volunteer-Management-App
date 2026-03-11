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
│   │   ├── seed.py                 # Seeds DB from backend/data/db.json if empty
│   │   └── migrations/
│   │       └── 001_initial.sql     # CREATE TABLE statements for core schema (incl. signup reservations)
│   │
│   └── data/
│       └── db.json                 # Sample seed data (users, pantries, shifts)
│
└── frontend/
    ├── templates/
    │   └── dashboard.html          # Single HTML page — loaded by Flask's render_template()
    └── static/
        ├── css/
        │   └── dashboard.css
        └── js/
            ├── api-helpers.js      # Core fetch wrapper: apiGet/apiPost/apiPatch/apiDelete
            ├── user-functions.js   # getCurrentUser(), userHasRole(), createUser()
            ├── admin-functions.js  # getPantries(), createPantry(), addPantryLead()
            ├── lead-functions.js   # getShifts(), createShift(), updateShift(), markAttendance()
            ├── volunteer-functions.js  # signupForShift(), cancelSignup(), reconfirmSignup()
            └── dashboard.js        # App entry point: boot sequence, UI state, event handlers
```

---

## 2. Database Schema & Table Relationships

All tables are created from SQL files in [backend/db/migrations/](backend/db/migrations/) via `init_schema()` on every Flask startup (idempotent — uses `CREATE TABLE IF NOT EXISTS` for the schema baseline).

```
roles               users
─────               ─────
role_id (PK)        user_id (PK)
role_name           full_name
                    email
        └──────────── password_hash
                    is_active
                    created_at / updated_at
         │
    user_roles (join table)
    ─────────────────────────
    user_id (FK → users)
    role_id (FK → roles)
         │
         │         pantries
         │         ────────
         │         pantry_id (PK)
         │         name
         │         location_address
         │
    pantry_leads (join table)
    ─────────────────────────
    pantry_id (FK → pantries)
    user_id   (FK → users)
         │
       shifts
       ──────
       shift_id (PK)
       pantry_id  (FK → pantries, CASCADE DELETE)
       shift_name
       start_time / end_time
       status          ← OPEN | FULL | CANCELLED
       created_by (FK → users)
         │
    shift_roles
    ───────────
    shift_role_id (PK)
    shift_id    (FK → shifts, CASCADE DELETE)
    role_title
    required_count
    filled_count    ← kept in sync by recalculate_shift_role_capacity()
    status          ← OPEN | FULL | CANCELLED
         │
    shift_signups
    ─────────────
    signup_id (PK)
    shift_role_id (FK → shift_roles, CASCADE DELETE)
    user_id       (FK → users, CASCADE DELETE)
    signup_status ← CONFIRMED | PENDING_CONFIRMATION | WAITLISTED | CANCELLED | SHOW_UP | NO_SHOW
    reservation_expires_at ← nullable UTC datetime used for 48h reserved spots after shift edits
    UNIQUE (shift_role_id, user_id)  ← prevents double signup
```

**Cascade rules:** Deleting a pantry cascades to shifts → shift_roles → shift_signups. Deleting a user cascades out of signups and pantry_leads but is RESTRICTED if they created a shift.

---

## 3. Backend Module Chain

### Startup sequence (once, when `python app.py` runs)

```
app.py
  load_dotenv("backend/.env")           ← reads DATA_BACKEND, MYSQL_* vars
  create_backend()   [factory.py]
    │  DATA_BACKEND == "mysql"?
    ├─ YES →
    │    init_schema()  [db/init_schema.py]
    │      ensure_database_exists()      ← connects without DB name, CREATE DATABASE IF NOT EXISTS
    │      apply_sql(*.sql in migrations/)   ← CREATE TABLE IF NOT EXISTS baseline schema
    │    MySQLBackend()  [mysql_backend.py]
    │    backend.is_empty()?
    │      YES → seed_mysql_from_json("data/db.json")
    │    return MySQLBackend instance
    └─ NO  → return MemoryBackend instance
  backend = <chosen instance>            ← module-level singleton used by all routes
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

---

## 4. Data Serialization Path

Every value that comes out of MySQL is a raw Python dict with raw types (datetime objects, integers, etc.). Before it can be sent to the browser as JSON, it must be serialized. Here is the full chain for a shift:

```
MySQL row (cursor.fetchone())
  → raw dict: { "shift_id": 1, "start_time": datetime(2025,6,1,9,0), ... }

mysql_backend.py: _serialize_shift(row)
  → clean dict: { "shift_id": 1, "start_time": "2025-06-01T09:00:00Z", ... }
     (datetimes converted to ISO-8601 strings by _to_iso_z())

app.py: route handler attaches related data
  → enriched dict: { ..., "roles": [ {shift_role_id, role_title, ...}, ... ] }

app.py: jsonify(shift)
  → Flask serializes dict to JSON string, sets Content-Type: application/json

Browser: fetch() resolves → response.json()
  → JavaScript object: { shift_id: 1, start_time: "2025-06-01T09:00:00Z", roles: [...] }

lead-functions.js / volunteer-functions.js:
  formatDateTimeForDisplay(shift.start_time)  ← new Date(string) → locale string
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
dashboard.js  →  lead-functions.js:     getShifts(), getActiveShifts(), createShift(), updateShift(),
                                        deleteShift(), createShiftRole(), updateShiftRole(),
                                        deleteShiftRole(), getShiftRegistrations(), markAttendance()
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
  │       ← { user_id, email, roles: ["ADMIN", ...] }
  │       sets module-level: currentUser
  │       writes email/roles to #user-email, #user-role in DOM
  │
  ├─ 2. setupRoleBasedUI()        [dashboard.js:60]
  │       reads currentUser.roles
  │       shows/hides nav tabs:
  │         VOLUNTEER  → shows "My Shifts" tab
  │         PANTRY_LEAD or ADMIN → shows "Manage Shifts" tab
  │         ADMIN      → shows "Admin Panel" tab
  │       returns the default tab name to activate
  │
  ├─ 3. loadPantries()            [dashboard.js:121]
  │       getAllPantries()         [admin-functions.js]
  │         apiGet('/api/all_pantries')
  │         ← [ {pantry_id, name, ...}, ... ]
  │       sets module-level: allPublicPantries
  │       populates #pantry-select dropdown
  │       populates #assign-pantry dropdown (admin)
  │
  ├─ 4. setupEventListeners()     [dashboard.js:1152]
  │       attaches click handlers to nav tabs → activateTab()
  │       attaches submit to #create-shift-form → createShift() + createShiftRole() loop
  │       attaches submit to #create-pantry-form → createPantry()
  │       attaches click to #assign-lead-btn → addPantryLead()
  │       attaches change to #pantry-select → reloads shifts for selected pantry
  │
  └─ 5. activateTab(defaultTab)   [dashboard.js:91]
          shows the target tab's content div
          calls the appropriate loader:
            'calendar'   → loadCalendarShifts()
            'my-shifts'  → loadMyRegisteredShifts()
            'shifts'     → loadShiftsTable()
            'admin'      → loadPantries() + loadPantryLeads() + updatePantriesTable()
```

---

## 7. Request Lifecycle (Every API Call)

Every single API request from the browser follows this exact path:

```
dashboard.js calls a domain function
  e.g. createShift(pantryId, data)
        │
        ▼
lead-functions.js: createShift()
  apiPost(`/api/pantries/${pantryId}/shifts`, data)
        │
        ▼
api-helpers.js: apiCall(path, options)
  reads window.location.search               ← preserves ?user_id=X
  fullPath = '/api/pantries/1/shifts?user_id=4'
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
  user_has_role(4, "ADMIN")
    backend.get_user_roles(4)               ← SELECT role_name FROM roles JOIN user_roles ...
  validate payload fields
  backend.create_shift(pantry_id, ...)      ← MySQLBackend
        │
        ▼
mysql_backend.py: create_shift()
  with get_connection() as conn:            ← borrows from pool
    cursor.execute("INSERT INTO shifts ...")
    conn.commit()
    cursor.execute("SELECT * FROM shifts WHERE shift_id = LAST_INSERT_ID()")
    row = cursor.fetchone()
  return _serialize_shift(row)              ← datetimes → ISO strings
        │
        ▼  back in app.py
shift["roles"] = []
return jsonify(shift), 201                  ← Flask serializes to JSON, HTTP 201
        │
        ▼  HTTP 201 JSON response
        │
api-helpers.js: apiCall()
  response.ok == true
  return response.json()                    ← parsed JS object
        │
        ▼
lead-functions.js: createShift() returns shift
        │
        ▼
dashboard.js: receives shift object
  DOM update — appends shift card / refreshes table
  (no page reload)
```

---

## 8. Authentication Lifecycle

### Current State: Mock (Active)

There is no login. Identity is the `?user_id=` URL parameter, defaulting to user 4 (Admin). `api-helpers.js:apiCall()` automatically propagates this parameter on every request. Flask's `@app.before_request` reads it and stores it in `g` — Flask's per-request context object that is created fresh for each request and discarded after the response is sent.

### Planned: Firebase Auth (Not Yet Active)

> This documents the planned integration. Nothing below exists in the current codebase.

```
Browser: user submits login form
  firebase.auth().signInWithEmailAndPassword(email, password)
  ← Firebase returns a signed JWT (ID token, expires in 1 hour)

api-helpers.js: apiCall() — updated to:
  const token = await firebase.auth().currentUser.getIdToken()
  fetch(path, { headers: { 'Authorization': `Bearer ${token}` } })

app.py: @app.before_request — updated to:
  token = request.headers.get("Authorization", "").removeprefix("Bearer ")
  decoded = firebase_admin.auth.verify_id_token(token)  ← validates signature + expiry
  user = backend.get_user_by_firebase_uid(decoded["uid"])
  g.current_user_id = user["user_id"]

  ← if token missing/invalid: return 401 before route handler runs
  ← if user not in local DB: return 403

Token refresh: Firebase SDK calls onIdTokenChanged() silently — transparent to the user.
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
