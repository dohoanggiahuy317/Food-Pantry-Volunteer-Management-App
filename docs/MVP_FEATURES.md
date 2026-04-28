# Product goal and MVP definition

This document defines the product goal, MVP scope, user personas, functional requirements, and primary user journeys for the volunteer management app focused on reducing no-shows and understaffing at food pantries. It serves as a guide for development and a reference for stakeholders to align on expectations and priorities.

## 1. Goal
Reduce volunteer no-shows and last-minute understaffing at food pantries by making shifts easy to publish, easy to claim, and hard to forget (via reminders + confirmations), while giving managers visibility and backup coverage.  

### 1.1. MVP success metrics (define upfront)
- No-show rate: baseline vs after launch (e.g., reduce by 25–40%)
- Fill rate: % of shifts meeting minimum required volunteers 24 hours before start
- Confirmation rate: % of volunteers who click “Confirm” before shift
- Time-to-backfill: average time to fill a cancelled slot (using on-call)

### 1.2. MVP scope (what to build first)

#### MVP includes
1.	Pantry creates shifts (role, time, needed count)  
2.	Public volunteer signup link (name/phone/email)  
3.	Automated reminders (T-48h and same-day) with Confirm/Cancel  
4.	Manager attendance marking after shift  
5.	Reliability score (simple)  
6.	On-call list + broadcast when understaffed  

#### Defer (V1.1+)
- Auto overbooking based on history  
- Multi-location pantries, complex roles permissions, recurring shift templates, deep analytics dashboards, integrations (Google Calendar), etc.

## 2. Personas and core jobs-to-be-done
### 2.1. Pantry Manager (Admin)
- Create/edit shifts, see staffing status, message volunteers, mark attendance, view reliability.
### 2.2. Shift Lead (Staff/Volunteer with permissions)
- View roster for a day, check-in volunteers on site, request backups if needed.
### 2.3. Volunteer
- Browse available shifts, sign up fast, confirm/cancel from phone, opt into on-call.

## 3. Functional requirements

### 3.1. Shift Management
Entities
- Pantry (org)
- Role (e.g., Packing, Check-in, Sorting)
- Shift (date/time, role, required_count, optional max_count)
Features
- Create shift: title/role, start/end time, required volunteer count
- Edit shift: time/capacity/role (with rules if volunteers already signed up)
- Cancel shift: notify signed-up volunteers
- Shift status: Open, Full, Closed, Cancelled, InProgress, Completed
Rules
- Signups allowed until configurable cutoff (default: 2 hours before start)
- Capacity: required_count = target; max_count optional (for future overbooking)

### 3.2. Volunteer Signup (Public)
- Public page lists open shifts (mobile-friendly)
- Volunteer fields (MVP):
  - Full name (required)
  - Phone (required for SMS reminders)
  - Email (optional but recommended)
- After signup:
  - Create a Signup record
  - Send confirmation message
  - Provide “Manage my signup” link (magic link token)
Anti-abuse
- Rate-limit signups per phone/email
- CAPTCHA optional (can defer until needed)

### 3.3. Reminders + Confirm/Cancel
Reminder schedule (configurable)
- T-48 hours
- T-6 hours or same-day morning (choose one for MVP)
Message content includes
- Shift details
- Two actions: Confirm / Cancel
Action handling
- Confirm → status becomes Confirmed
- Cancel → status becomes Cancelled and slot opens
- If no action → status remains Pending
Edge case rules
- If volunteer cancels within X hours of shift start, tag as LateCancel (optional in MVP; can just record timestamp)

### 3.4. Attendance Tracking
- Attendance marking UI for Admin/Lead:
  - ShowedUp, NoShow, Late, Excused, Cancelled
- Lock attendance after N days (optional)
- Export attendance CSV (nice-to-have but helpful for ops)

### 3.5. Reliability Score (Simple, MVP-safe)

A straightforward scoring model (transparent, easy to explain):
- Start at 100
- -20 for NoShow
- -10 for LateCancel (if implemented)
- -5 for Late
- +2 for ShowedUp (cap at 100)

Store:
- score_current
- total_shifts_signed_up
- total_showed
- total_no_show

Use:
- Admin roster view shows badge: Highly reliable / OK / Risky based on thresholds.

### 3.6. On-call / Backup List
- Volunteers can toggle “I’m on-call” with preferred days/times (MVP: just a boolean + optional availability notes)
- Admin can trigger broadcast:
  - target: on-call volunteers
  - message: “We need 2 people today 3–6pm. Reply YES to join.”
- First responders fill open slots:
  - Option A (simpler): first N “YES” automatically added
  - Option B (safer): collect responders → Admin clicks “Add” (recommended MVP)



## 4. Non-functional requirements

### 4.1. Reliability & delivery
- SMS/email delivery tracking: sent, delivered (if provider supports), failed
- Retry strategy for transient failures
- Idempotent endpoints for confirm/cancel links
- Current repo implementation includes Resend email delivery for signup confirmations, shift updates that require reconfirmation, and shift cancellations; shift times in those emails are localized with each user's saved timezone when available, with `America/New_York` as the fallback; sender setup still requires a verified domain/subdomain before production sending

### 4.2. Security & privacy
- Magic-link tokens for volunteer actions (no passwords for volunteers)
- Admin authentication (email/password or Google OAuth)
- Store only necessary PII (name, phone, email), encrypt at rest if possible
- Basic audit log: who changed shift, who marked attendance

### 4.3. Compliance notes (pragmatic)
- SMS opt-out language (“Reply STOP”) if using providers like Twilio
- Consent checkbox during signup: “I agree to receive shift reminders by SMS/email.”



## 5. Primary user journeys

### Journey A: Create and publish shifts
1.	Admin logs in → creates shift(s) with date/time/role/capacity
2.	Admin shares a public signup link (per pantry or per event/day)
### Journey B: Volunteer signs up and gets reminders
1.	Volunteer opens link → sees list/calendar of shifts
2.	Picks shift → enters name + phone + email → submits
3.	Gets confirmation message immediately
4.	Gets reminder messages with Confirm/Cancel
5.	If cancels → slot reopens automatically
### Journey C: Day-of operations + attendance + reliability
1.	Admin/Lead views roster
2.	After shift ends → marks each signup as Show/No-show/Late/Excused
3.	Reliability score updates
### Journey D: On-call backfill
1.	Shift becomes understaffed (cancellations/no confirmations)
2.	Admin triggers “Request on-call”
3.	System messages on-call list
4.	First X responders are added to shift (or Admin approves, depending on safety preference)
 
## 6. User stories

### Admin stories
- As an Admin, I can create a shift with date/time/role/capacity so volunteers can sign up.
- As an Admin, I can share a signup link so volunteers can access shifts without logging in.
- As an Admin, I can view a roster for each shift so I know who is coming.
- As an Admin, I can see which volunteers confirmed so I can forecast staffing.
- As an Admin, I can mark attendance after the shift so the system can track reliability.
- As an Admin, I can trigger an on-call request if staffing drops so I can backfill quickly.

### Volunteer stories
- As a Volunteer, I can view available shifts on my phone so I can pick one quickly.
- As a Volunteer, I can sign up with my name/phone/email so I receive reminders.
- As a Volunteer, I can see shift times in my browser's local timezone and receive emails in my saved account timezone.
- As a Volunteer, I can confirm via a link so the pantry knows I’m coming.
- As a Volunteer, I can cancel via a link so the slot opens for someone else.
- As a Volunteer, I can opt into on-call so I can help when emergencies happen.

### System stories (backend)
- As the System, I send confirmation messages immediately after signup.
- As the System, I send reminder messages at configured times.
- As the System, I update signup status when a volunteer confirms/cancels.
- As the System, I log message delivery + link clicks for troubleshooting/auditing.

## Attendance + Credibility (Implemented Rules)

- Attendance outcomes are stored in `shift_signups.signup_status` using:
  - `SHOW_UP`
  - `NO_SHOW`
- Attendance marking endpoint:
  - `PATCH /api/signups/{signup_id}/attendance`
  - Body: `{ "attendance_status": "SHOW_UP" | "NO_SHOW" }`
- Permission:
  - Pantry lead for that shift's pantry, or admin.
- Time window:
  - Opens 15 minutes before shift start.
  - Closes 6 hours after shift end.
- Volunteer credibility in My Shifts:
  - `attended / total_marked_past_shifts`
  - numerator counts `SHOW_UP`
  - denominator counts past shifts marked as `SHOW_UP` or `NO_SHOW`
