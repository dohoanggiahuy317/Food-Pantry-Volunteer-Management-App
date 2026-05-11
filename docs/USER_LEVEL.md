# User-Level Documentation

This document explains the Volunteer Management System by user role. It describes what each role can do, where to do it in the dashboard, and the key rules that affect each action.

## 0. Table of Contents
- [User-Level Documentation](#user-level-documentation)
  - [0. Table of Contents](#0-table-of-contents)
  - [1. Audience and Scope](#1-audience-and-scope)
  - [2. Accessing the App](#2-accessing-the-app)
  - [3. Role Summary](#3-role-summary)
  - [4. Volunteer Role](#4-volunteer-role)
    - [4.1 What Volunteers Can Do](#41-what-volunteers-can-do)
    - [4.2 Volunteer: Sign Up or Log In](#42-volunteer-sign-up-or-log-in)
    - [4.3 Volunteer: Browse Available Shifts](#43-volunteer-browse-available-shifts)
    - [4.4 Volunteer: Sign Up for a Shift](#44-volunteer-sign-up-for-a-shift)
    - [4.5 Volunteer: Manage Registered Shifts](#45-volunteer-manage-registered-shifts)
    - [4.6 Volunteer: Cancel a Signup](#46-volunteer-cancel-a-signup)
    - [4.7 Volunteer: Reconfirm a Changed Shift](#47-volunteer-reconfirm-a-changed-shift)
    - [4.8 Volunteer: Use the Pantry Directory](#48-volunteer-use-the-pantry-directory)
    - [4.9 Volunteer: Manage Account](#49-volunteer-manage-account)
    - [4.10 Volunteer: Google Calendar Sync](#410-volunteer-google-calendar-sync)
    - [4.11 Volunteer: Attendance and Score](#411-volunteer-attendance-and-score)
  - [5. Pantry Lead Role](#5-pantry-lead-role)
    - [5.1 What Pantry Leads Can Do](#51-what-pantry-leads-can-do)
    - [5.2 Pantry Lead: Assigned Pantry Scope](#52-pantry-lead-assigned-pantry-scope)
    - [5.3 Pantry Lead: Create a One-Time Shift](#53-pantry-lead-create-a-one-time-shift)
    - [5.4 Pantry Lead: Create a Recurring Shift](#54-pantry-lead-create-a-recurring-shift)
    - [5.5 Pantry Lead: Review Shift Coverage](#55-pantry-lead-review-shift-coverage)
    - [5.6 Pantry Lead: Edit a Shift](#56-pantry-lead-edit-a-shift)
    - [5.7 Pantry Lead: Cancel a Shift](#57-pantry-lead-cancel-a-shift)
    - [5.8 Pantry Lead: Send a Help Broadcast](#58-pantry-lead-send-a-help-broadcast)
    - [5.9 Pantry Lead: Take Attendance](#59-pantry-lead-take-attendance)
  - [6. Admin Role](#6-admin-role)
    - [6.1 What Admins Can Do](#61-what-admins-can-do)
    - [6.2 Admin: Manage Pantries](#62-admin-manage-pantries)
    - [6.3 Admin: Assign Pantry Leads](#63-admin-assign-pantry-leads)
    - [6.4 Admin: Manage Users](#64-admin-manage-users)
    - [6.5 Admin: Change User Roles](#65-admin-change-user-roles)
    - [6.6 Admin: Manage Shifts Across Pantries](#66-admin-manage-shifts-across-pantries)
  - [7. Super Admin Role](#7-super-admin-role)
    - [7.1 What Super Admins Can Do](#71-what-super-admins-can-do)
    - [7.2 Protected Super Admin Account](#72-protected-super-admin-account)
    - [7.3 Super Admin Best Practices](#73-super-admin-best-practices)
  - [8. Shared Account Capabilities](#8-shared-account-capabilities)
    - [8.1 Timezone Behavior](#81-timezone-behavior)
    - [8.2 Account Deletion](#82-account-deletion)
  - [9. Public User Capabilities](#9-public-user-capabilities)
  - [10. Capability Matrix](#10-capability-matrix)
  - [11. Common Error Messages by Role](#11-common-error-messages-by-role)
    - [Volunteer Errors](#volunteer-errors)
    - [Pantry Lead Errors](#pantry-lead-errors)
    - [Admin Errors](#admin-errors)
  - [12. Role-Based Best Practices](#12-role-based-best-practices)
    - [Volunteer Best Practices](#volunteer-best-practices)
    - [Pantry Lead Best Practices](#pantry-lead-best-practices)
    - [Admin Best Practices](#admin-best-practices)
    - [Super Admin Best Practices](#super-admin-best-practices)

## 1. Audience and Scope

This guide is for people who use the application, not developers maintaining the code. It is organized by role:

- Volunteer
- Pantry Lead
- Admin
- Super Admin

Each role section lists the capabilities available to that role and the practical workflows attached to those capabilities.

## 2. Accessing the App

The main application is available at `/dashboard`.

The dashboard starts with an authentication screen. Depending on the environment, users may see:

- Demo sample accounts in memory-auth mode.
- Google login and Google signup in Firebase auth mode.

After login, the dashboard shows only the tabs and actions that match the user's role.

Common dashboard tabs:

- `Calendar`
- `My Shifts`
- `Pantries`
- `My Account`
- `Manage Shifts`
- `Admin Panel`

Not every user sees every tab.

## 3. Role Summary

| Role | Main Purpose | Main Tabs |
| --- | --- | --- |
| Volunteer | Find shifts, sign up, manage personal commitments, subscribe to pantry updates. | Calendar, My Shifts, Pantries, My Account |
| Pantry Lead | Manage shifts and registrations for assigned pantries. | Calendar, Manage Shifts, My Account |
| Admin | Manage pantries, pantry leads, users, roles, and shifts across the system. | Calendar, Manage Shifts, Admin Panel, My Account |
| Super Admin | Highest administrative role with protected access controls. | Calendar, Manage Shifts, Admin Panel, My Account |

Users can technically have role combinations, but the admin user-management workflow treats normal users as having one editable role at a time.

## 4. Volunteer Role

Volunteers are the primary users who browse shifts and register for pantry work.

### 4.1 What Volunteers Can Do

Volunteers can:

- Log in or sign up with Google when Firebase auth is enabled.
- Use sample-account login when the app is running in demo memory-auth mode.
- View available shifts in the calendar.
- Search and filter available shifts.
- Open shift details.
- Sign up for an open role in a shift.
- View all of their registered shifts.
- Cancel their own signups.
- Reconfirm changed shifts.
- Browse the pantry directory.
- Subscribe to pantry update emails.
- Unsubscribe from pantry update emails.
- Update basic account information.
- View account summary and attendance score.
- Connect Google Calendar auto sync when available.
- Disconnect Google Calendar auto sync.
- Start a supported email-change flow.
- Delete their own account, except for the protected super admin account.
- Log out.

### 4.2 Volunteer: Sign Up or Log In

Google signup creates a volunteer account by default.

Volunteer Google signup steps:

1. Open `/dashboard`.
2. Select `Sign Up With Google`.
3. Choose a Google account.
4. Enter full name.
5. Enter phone number.
6. Complete signup.
7. Return to the dashboard.

Volunteer Google login steps:

1. Open `/dashboard`.
2. Select `Log In With Google`.
3. Choose the Google account linked to the app user.
4. Wait for the dashboard to load.

Demo login steps:

1. Open `/dashboard`.
2. Choose a sample account from the login panel.
3. Wait for the dashboard to load.

### 4.3 Volunteer: Browse Available Shifts

Volunteers use the `Calendar` tab to browse available shifts.

Available calendar actions:

- Switch between month, week, and day views.
- Move to previous or next calendar ranges.
- Jump to today.
- Search shifts, pantry names, and role names.
- Filter by pantry.
- Filter by time bucket.
- Clear filters.
- Open shift details.

Shift details can include:

- Shift name.
- Pantry name.
- Pantry address.
- Shift date and time.
- Roles or positions.
- Required volunteer count.
- Filled count.
- Capacity status.
- Recurring shift information.

### 4.4 Volunteer: Sign Up for a Shift

Volunteers can sign up for open shift roles.

Signup steps:

1. Open the `Calendar` tab.
2. Find a shift.
3. Open the shift details.
4. Review the pantry, date, time, and role list.
5. Select an available role.
6. Confirm the signup action.
7. Wait for the success message.
8. Confirm the shift appears in `My Shifts`.

Signup rules:

- The user must have the `VOLUNTEER` role.
- Volunteers can only sign themselves up.
- The shift must not be cancelled.
- The shift must not have ended.
- The selected role must not be cancelled.
- The selected role must have capacity.
- The user cannot sign up for overlapping active shifts.
- The user cannot exceed the rolling signup limit.

Current rolling signup limit:

- At most 5 signups in 24 hours.

### 4.5 Volunteer: Manage Registered Shifts

Volunteers use the `My Shifts` tab to manage existing commitments.

Available actions:

- View registered shifts in calendar format.
- View registered shifts in list format.
- Search registered shifts.
- Filter by pantry.
- Filter by time bucket.
- Filter by status.
- Sort the list.
- Open registered shift details.
- Cancel a signup.
- Reconfirm a pending signup.

Common signup statuses:

- `CONFIRMED`: the volunteer has an active slot.
- `PENDING_CONFIRMATION`: the shift changed and the volunteer must reconfirm.
- `WAITLISTED`: reconfirmation could not preserve the slot.
- `SHOW_UP`: attendance was marked as present.
- `NO_SHOW`: attendance was marked as absent.

### 4.6 Volunteer: Cancel a Signup

Cancellation steps:

1. Open `My Shifts`.
2. Find the signup.
3. Select the cancel action.
4. Confirm the browser prompt.
5. Wait for the success message.

Cancellation effects:

- The signup is removed from the volunteer's active commitments.
- The role capacity is recalculated.
- If Google Calendar sync is connected, the app tries to remove the linked calendar event.

### 4.7 Volunteer: Reconfirm a Changed Shift

A shift may require reconfirmation after a pantry lead or admin changes the shift time, status, roles, or capacity.

Reconfirmation steps:

1. Open `My Shifts`.
2. Find the signup marked `PENDING_CONFIRMATION`.
3. Review the changed shift information.
4. Choose confirm or cancel.
5. Confirm the browser prompt.
6. Wait for the result message.

Possible outcomes:

- Confirmed successfully: the signup returns to `CONFIRMED`.
- Cancelled successfully: the signup is removed.
- Role full or unavailable: capacity is no longer available.
- Reservation expired: the reconfirmation window ended.

Important rule:

- Pending signups reserve capacity for a limited time. If the reservation expires, the volunteer must sign up again if capacity remains.

### 4.8 Volunteer: Use the Pantry Directory

Volunteers use the `Pantries` tab to browse pantry locations and manage subscription preferences.

Available actions:

- Search pantries by name or address.
- Sort pantry listings.
- Filter by all, subscribed, or unsubscribed pantries.
- Select a pantry and view details.
- Preview upcoming shifts for a pantry.
- Subscribe to a pantry.
- Unsubscribe from a pantry.

Subscription behavior:

- Subscribing allows the app to send new-shift emails for that pantry when notifications are configured.
- Unsubscribing stops new-shift subscription emails for that pantry.
- Unsubscribing does not cancel existing shift signups.

### 4.9 Volunteer: Manage Account

Volunteers use the `My Account` tab for personal settings.

Available actions:

- View account summary.
- Update full name.
- Update phone number.
- View saved email address.
- Start an email-change flow when supported.
- View browser timezone information.
- Connect Google Calendar sync.
- Disconnect Google Calendar sync.
- Delete account.

Account rules:

- Full name is required.
- Phone number can be changed from the account form.
- Email changes are supported only in eligible Firebase-linked account states.
- Account deletion is permanent.

### 4.10 Volunteer: Google Calendar Sync

When enabled and configured, Google Calendar sync can:

- Create an event when the volunteer signs up for a shift.
- Update an event when the signup or shift changes.
- Remove an event when the signup is cancelled.
- Remove an event when the signup becomes waitlisted or expired.
- Remove synced events when the volunteer disconnects Google Calendar.

Calendar sync requirements:

- The account must use Google/Firebase login.
- The server must have Google OAuth configured.
- The user must complete the Google Calendar OAuth popup.

### 4.11 Volunteer: Attendance and Score

Volunteers cannot mark their own attendance.

Attendance can be marked by:

- A pantry lead assigned to the shift's pantry.
- An admin-capable user.

Attendance statuses:

- `SHOW_UP`
- `NO_SHOW`

The volunteer's attendance score is shown in account and admin views.

## 5. Pantry Lead Role

Pantry leads manage operational shifts for assigned pantries.

### 5.1 What Pantry Leads Can Do

Pantry leads can:

- View shifts for pantries they manage.
- Create one-time shifts for assigned pantries.
- Create recurring shifts for assigned pantries.
- Add roles or positions to shifts.
- Set required volunteer counts.
- Edit upcoming shifts for assigned pantries.
- Edit roles and required counts for assigned pantry shifts.
- Cancel shifts for assigned pantries.
- Cancel only one recurring occurrence.
- Cancel this and following recurring occurrences.
- View registrations for assigned pantry shifts.
- See role coverage and pending reconfirmation counts.
- Send help broadcasts for assigned pantry shifts.
- Take attendance for assigned pantry shifts.
- Mark registered volunteers as `SHOW_UP` or `NO_SHOW`.
- Use their own `My Account` tab.
- Log out.

Pantry leads cannot:

- Manage pantries unless they are also admin-capable.
- Assign themselves to pantries.
- Edit users or roles unless they are also admin-capable.
- Manage shifts for pantries where they are not assigned.

### 5.2 Pantry Lead: Assigned Pantry Scope

Pantry lead permissions are pantry-specific.

The lead can manage a shift only when:

- The user has the `PANTRY_LEAD` role.
- The user is assigned as a lead for that shift's pantry.

If a pantry lead sees a forbidden message, the most common reason is that they are not assigned to the selected pantry.

### 5.3 Pantry Lead: Create a One-Time Shift

Create-shift steps:

1. Open `Manage Shifts`.
2. Select an assigned pantry if the pantry selector is visible.
3. Select `Create Shift`.
4. Enter shift name.
5. Enter start date and time.
6. Enter end date and time.
7. Add at least one role.
8. Enter each role title.
9. Enter each required count.
10. Select `Create Shift with Roles`.
11. Wait for the success message.

Role rules:

- Each role must have a title.
- Each role must have required count of at least 1.
- A shift created through full-create must include at least one role.

### 5.4 Pantry Lead: Create a Recurring Shift

Recurring-shift steps:

1. Open `Manage Shifts`.
2. Start creating a shift.
3. Turn on `Repeat`.
4. Set the weekly interval.
5. Select weekdays.
6. Choose how the series ends:
   - After a fixed number of occurrences.
   - On an until date.
7. Add roles and required counts.
8. Select `Create Shift with Roles`.
9. Wait for the success message.

Recurring rules:

- Current recurrence is weekly.
- The recurrence must have a finite end.
- The app creates concrete shift rows for each occurrence.
- Each occurrence links back to the same series.

### 5.5 Pantry Lead: Review Shift Coverage

Pantry leads can inspect coverage in `Manage Shifts`.

Coverage information can include:

- Shift status.
- Role names.
- Required counts.
- Filled counts.
- Open or full role status.
- Registered volunteers.
- Pending reconfirmation count.

This helps pantry leads identify understaffed shifts.

### 5.6 Pantry Lead: Edit a Shift

Edit steps:

1. Open `Manage Shifts`.
2. Select a shift.
3. Open the edit panel.
4. Change shift details or roles.
5. Select `Save Shift Changes`.
6. If prompted for recurring scope, choose:
   - This event only.
   - This and following events.
7. Wait for the success message.

Shift edits can affect existing volunteers.

Actions that may require volunteer reconfirmation:

- Changing shift start or end time.
- Cancelling a shift.
- Changing role capacity.
- Removing a role with signups.
- Cancelling a role with signups.
- Updating a recurring series slice.

When reconfirmation is required:

- Affected signups move to `PENDING_CONFIRMATION`.
- Volunteers may receive update emails.
- Volunteers must reconfirm before the reservation expires.

### 5.7 Pantry Lead: Cancel a Shift

Cancel steps:

1. Open `Manage Shifts`.
2. Select the target shift.
3. Choose the cancel action.
4. If recurring, choose the cancellation scope.
5. Confirm the browser prompt.
6. Wait for the success message.

Cancellation effects:

- The shift status changes to cancelled.
- New signups are blocked.
- Affected volunteers may be notified.
- Existing signups may require action or become unavailable depending on the flow.

### 5.8 Pantry Lead: Send a Help Broadcast

Help broadcasts are used when a shift needs more coverage.

Broadcast steps:

1. Open `Manage Shifts`.
2. Select the understaffed shift.
3. Select `Broadcast Help`.
4. Review suggested volunteers.
5. Search by name or email if needed.
6. Select recipients.
7. Select `Send Broadcast`.
8. Review the result message.

Broadcast rules:

- The sender must be allowed to manage the shift.
- The shift cannot be ended.
- The shift cannot be cancelled.
- Recipients must be volunteers.
- The recipient limit is 25 volunteers.
- A sender cooldown prevents repeated broadcasts too quickly.

### 5.9 Pantry Lead: Take Attendance

Attendance steps:

1. Open `Manage Shifts`.
2. Select a shift.
3. Select `Take Attendance`.
4. Search registrants if needed.
5. Mark each volunteer as `SHOW_UP` or `NO_SHOW`.
6. Close the modal.

Attendance window:

- Opens 15 minutes before shift start.
- Closes 6 hours after shift end.

Attendance effects:

- The signup status changes.
- The volunteer attendance score updates.
- Attendance outcomes remain visible to managers.

## 6. Admin Role

Admins manage the overall system. They can perform pantry administration, user management, and cross-pantry shift management.

### 6.1 What Admins Can Do

Admins can:

- View all pantries.
- Create pantries.
- Edit pantries.
- Delete pantries.
- Assign pantry leads.
- Remove pantry leads.
- Search users.
- View user profiles.
- View user signup history.
- Filter users by role.
- Update normal user roles.
- Create shifts for any pantry.
- Edit shifts for any pantry.
- Cancel shifts for any pantry.
- View registrations for any shift.
- Send help broadcasts for any shift.
- Take attendance for any shift.
- Manage their own account.
- Connect or disconnect Google Calendar sync for their own account when eligible.
- Log out.

Admins cannot:

- Assign `SUPER_ADMIN` through the normal role-management endpoint.
- Edit the protected super admin account.
- Remove `ADMIN` from another admin unless they are a super admin.

### 6.2 Admin: Manage Pantries

Admins use `Admin Panel` -> `Manage Pantries`.

Available pantry actions:

- Create a pantry.
- Search pantries.
- Select a pantry.
- Edit pantry name.
- Edit pantry address.
- Delete a pantry.
- View assigned pantry leads.
- Assign eligible pantry leads.
- Remove pantry leads.

Create-pantry steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. Enter pantry name.
4. Enter pantry address.
5. Select `Create Pantry`.
6. Wait for the success message.

Edit-pantry steps:

1. Search or select the pantry.
2. Open the edit action.
3. Update name or address.
4. Save.
5. Wait for the success message.

Delete-pantry steps:

1. Search or select the pantry.
2. Choose delete.
3. Confirm the browser prompt.
4. Wait for the success message.

Important deletion effect:

- Deleting a pantry removes dependent pantry leads, subscriptions, shifts, shift roles, and shift signups through cascade behavior.

### 6.3 Admin: Assign Pantry Leads

A user must have the `PANTRY_LEAD` role before being assigned to a pantry.

Assign-lead steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. Select a pantry.
4. Search eligible pantry lead users.
5. Select the lead.
6. Add the lead.
7. Wait for the success message.

Remove-lead steps:

1. Select the pantry.
2. Find the assigned lead.
3. Choose remove.
4. Confirm the browser prompt.
5. Wait for the success message.

Removing a lead assignment does not delete the user's account.

### 6.4 Admin: Manage Users

Admins use `Admin Panel` -> `Manage Users`.

Available user actions:

- Search by full name.
- Search by email.
- Filter by role.
- View user result table.
- Open a user profile.
- Review user account details.
- Review user signup history.
- Review attendance score.
- Update editable user role.

Search-user steps:

1. Open `Admin Panel`.
2. Select `Manage Users`.
3. Enter name or email search text.
4. Optionally choose a role filter.
5. Select `Search Users`.

Open-profile steps:

1. Search users.
2. Select a user from the results.
3. Review the user profile panel.

### 6.5 Admin: Change User Roles

Role-change steps:

1. Open a user profile.
2. Select one editable role.
3. Save the role change.
4. Wait for the success message.

Role-change rules:

- Exactly one editable role must be selected.
- `SUPER_ADMIN` cannot be assigned through this flow.
- The protected super admin account cannot be edited.
- A non-super-admin cannot remove `ADMIN` from another admin.
- Role changes affect what tabs and actions the user sees after refresh or next login.

### 6.6 Admin: Manage Shifts Across Pantries

Admins can use `Manage Shifts` for any pantry.

Admin shift capabilities:

- Select any pantry.
- Create one-time shifts.
- Create recurring shifts.
- Edit shift details.
- Edit shift roles.
- Cancel shifts.
- Cancel future recurring occurrences.
- View registrations.
- Send help broadcasts.
- Take attendance.

The shift-management rules are the same as pantry lead rules, but admins are not limited to assigned pantries.

## 7. Super Admin Role

Super admins are admin-capable users with the highest operational authority.

### 7.1 What Super Admins Can Do

Super admins can do everything admins can do, including:

- Manage all pantries.
- Manage all shift workflows.
- Search and monitor users.
- Update normal user roles.
- Remove `ADMIN` from another admin.
- Preserve top-level access when normal admin permissions need to be corrected.

### 7.2 Protected Super Admin Account

The protected seeded super admin account has special restrictions.

Protected account rules:

- Its roles cannot be edited through the dashboard.
- It cannot delete itself.
- It should remain available as a recovery account.

### 7.3 Super Admin Best Practices

Super admins should:

- Keep at least one trusted super admin account available.
- Avoid using the protected account for routine daily work if another admin account is available.
- Use role changes carefully because they directly change access.
- Remove admin access from users only when operationally necessary.

## 8. Shared Account Capabilities

All logged-in users can use `My Account`.

Shared account actions:

- View account summary.
- Update full name.
- Update phone number.
- View account email.
- View current roles.
- View attendance score when available.
- View timezone note.
- Start email change when supported.
- Connect Google Calendar when eligible.
- Disconnect Google Calendar when connected.
- Delete own account when allowed.
- Log out.

### 8.1 Timezone Behavior

The browser sends timezone information with API requests.

Timezone is used for:

- Showing times in the browser's local timezone.
- Saving the user's preferred timezone.
- Formatting email notification shift times.

If a user has no saved timezone, notification emails use `America/New_York` as a fallback.

### 8.2 Account Deletion

Account deletion:

- Removes the local app user.
- Signs the user out.
- Deletes the linked Firebase user in Firebase mode after fresh reauthentication.
- Removes dependent records according to database cascade rules.

The protected super admin account cannot delete itself.

## 9. Public User Capabilities

People who are not logged in can still access public pages.

Public pages:

- `/`
- `/privacy`
- `/terms`
- `/term`

Public API visibility:

- Public pantry listing.
- Public shifts for a pantry slug.

Public pages support product discovery and Google OAuth verification.

## 10. Capability Matrix

| Capability | Volunteer | Pantry Lead | Admin | Super Admin |
| --- | --- | --- | --- | --- |
| Log in | Yes | Yes | Yes | Yes |
| Browse available shifts | Yes | Yes | Yes | Yes |
| Sign up for shifts | Yes | Only if also volunteer | Only if also volunteer | Only if also volunteer |
| Cancel own signup | Yes | Yes, for own signup | Yes | Yes |
| Reconfirm own signup | Yes | Yes, for own signup | Yes | Yes |
| Browse pantry directory | Yes | Yes | Yes | Yes |
| Subscribe to pantry updates | Yes | Only if also volunteer | Only if also volunteer | Only if also volunteer |
| Update own profile | Yes | Yes | Yes | Yes |
| Connect own Google Calendar | If eligible | If eligible | If eligible | If eligible |
| Create shifts | No | Assigned pantries | All pantries | All pantries |
| Edit shifts | No | Assigned pantries | All pantries | All pantries |
| Cancel shifts | No | Assigned pantries | All pantries | All pantries |
| View registrations | No | Assigned pantries | All pantries | All pantries |
| Send help broadcasts | No | Assigned pantries | All pantries | All pantries |
| Mark attendance | No | Assigned pantries | All pantries | All pantries |
| Create pantries | No | No | Yes | Yes |
| Edit pantries | No | No | Yes | Yes |
| Delete pantries | No | No | Yes | Yes |
| Assign pantry leads | No | No | Yes | Yes |
| Search users | No | No | Yes | Yes |
| Edit user roles | No | No | Restricted | Restricted, highest authority |
| Assign SUPER_ADMIN | No | No | No | No through dashboard |
| Edit protected super admin | No | No | No | No |

## 11. Common Error Messages by Role

### Volunteer Errors

`Forbidden or not a volunteer`

- The account does not have the `VOLUNTEER` role for signup.

`Already signed up`

- The volunteer already has a signup for the selected role.

`Can't register for overlapping shift`

- The volunteer has another active signup that overlaps the selected shift.

`SIGNUP_RATE_LIMITED`

- The volunteer reached the rolling 24-hour signup limit.

`ROLE_FULL_OR_UNAVAILABLE`

- The role is full, cancelled, or unavailable during reconfirmation.

`RESERVATION_EXPIRED`

- The pending reconfirmation window expired.

### Pantry Lead Errors

`Not a lead for this pantry`

- The pantry lead role exists, but the user is not assigned to that pantry.

`Forbidden`

- The user is missing permission for the action.

`PAST_SHIFT_LOCKED`

- The shift has ended and can no longer be edited.

`Cannot broadcast help for a cancelled shift`

- Help broadcasts are blocked for cancelled shifts.

### Admin Errors

`The protected super admin account cannot have its roles edited`

- The selected account is protected.

`The SUPER_ADMIN role cannot be assigned through this endpoint`

- Super admin assignment is blocked in normal role management.

`Only the super admin can remove ADMIN from another admin`

- A normal admin attempted to remove another admin's admin role.

## 12. Role-Based Best Practices

### Volunteer Best Practices

- Keep contact information current.
- Check `My Shifts` after signing up.
- Reconfirm changed shifts promptly.
- Cancel as early as possible if unable to attend.
- Subscribe only to pantries where updates are useful.
- Use Google Calendar sync if available and helpful.

### Pantry Lead Best Practices

- Create shifts early.
- Use clear shift names.
- Use role names that volunteers understand.
- Set realistic required counts.
- Review coverage before shift day.
- Use help broadcasts only when coverage is genuinely needed.
- Mark attendance during the allowed attendance window.
- Avoid late changes unless necessary because volunteers may need to reconfirm.

### Admin Best Practices

- Assign pantry leads deliberately.
- Keep user roles simple.
- Avoid deleting pantries unless dependent data should be removed.
- Confirm notification and calendar configuration before operational reliance.
- Review user role changes carefully.

### Super Admin Best Practices

- Preserve recovery access.
- Use elevated actions sparingly.
- Do not use the protected account for routine work when another admin account is available.
- Keep role changes auditable through operational practice.

