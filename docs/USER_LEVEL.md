# User-Level Documentation

This guide explains how to use the Volunteer Management System from the perspective of volunteers, pantry leads, administrators, and super administrators. It focuses on what users see, what each role can do, and how to complete common tasks in the dashboard.

## 1. Product Overview

The Volunteer Management System helps food pantry teams publish volunteer shifts, fill required roles, track registrations, notify volunteers, and record attendance. Volunteers use the system to find open shifts, sign up, manage upcoming commitments, and keep their personal details current.

The app has two main areas:

- Public pages: homepage, privacy policy, terms, and public pantry shift listings.
- Authenticated dashboard: the main workspace at `/dashboard`.

The dashboard adapts to the logged-in user's role. A volunteer sees volunteer-focused tabs, while pantry leads and admins also see shift-management and administration tools.

## 2. User Roles

### Volunteer

Volunteers can:

- Browse available shifts.
- Search and filter the shift calendar.
- Sign up for open shift roles.
- View their registered shifts.
- Cancel their own signups.
- Reconfirm shifts after schedule or capacity changes.
- Subscribe or unsubscribe from pantry updates.
- Maintain their account name, phone number, email, and timezone.
- Connect Google Calendar sync when Google/Firebase auth and server OAuth are configured.
- Delete their account, unless they are the protected super admin account.

### Pantry Lead

Pantry leads can:

- Manage shifts for pantries assigned to them.
- Create one-time and recurring shifts.
- Add roles and required volunteer counts.
- Edit upcoming shifts.
- Cancel single shifts or future recurring shifts.
- View registrations for managed shifts.
- Send help broadcasts to selected volunteers.
- Mark attendance during the allowed attendance window.

Pantry leads cannot manage pantries unless they also have an admin-capable role.

### Admin

Admins can:

- Manage all pantries.
- Create, edit, and delete pantries.
- Assign and remove pantry leads.
- Search and monitor users.
- Edit normal user roles within system restrictions.
- Manage shifts across all pantries.
- View user profiles and user signup history.

Admins cannot assign the `SUPER_ADMIN` role.

### Super Admin

Super admins have admin-capable access plus higher protection authority.

The protected seeded super admin account:

- Cannot have its roles edited through the app.
- Cannot delete itself.
- Is intended to prevent accidental loss of administrative access.

## 3. Signing In

The sign-in experience depends on the environment configuration.

### Demo or Local Memory Login

In memory-auth mode, the login page shows sample accounts.

Steps:

1. Open `/dashboard`.
2. Wait for the login panel to load.
3. Choose one sample account from the list.
4. The page reloads into the dashboard.

Sample accounts are intended for local development and demonstrations.

### Google Login

In Firebase/Google auth mode, the login panel shows Google login buttons.

Steps:

1. Open `/dashboard`.
2. Select `Log In With Google`.
3. Choose a Google account in the popup.
4. If the account already exists in the app, the dashboard opens.
5. If the account is new, the app may ask you to complete volunteer signup.

Google login requires the Google account email to be verified.

### Google Volunteer Signup

Steps:

1. Open `/dashboard`.
2. Select `Sign Up With Google`.
3. Choose a Google account in the popup.
4. Enter your full name.
5. Enter your phone number.
6. Submit the signup form.
7. The app creates your volunteer account and opens the dashboard.

New Google signups receive the `VOLUNTEER` role by default.

## 4. Dashboard Layout

The main dashboard contains a top header, role-aware navigation tabs, and the selected tab content.

Common tabs:

- `Calendar`: available shifts across pantries.
- `My Shifts`: shifts you registered for.
- `Pantries`: volunteer pantry directory and subscription controls.
- `My Account`: profile, email, calendar sync, and account deletion.

Manager and admin tabs:

- `Manage Shifts`: create, edit, cancel, inspect, broadcast, and take attendance for shifts.
- `Admin Panel`: manage pantries, pantry leads, users, and roles.

Some tabs are hidden if your role does not allow that workflow.

## 5. Calendar Tab

The Calendar tab is the main place to discover available shifts.

### What You Can See

Each shift can show:

- Shift name.
- Pantry name.
- Pantry location.
- Start and end time.
- Available roles.
- Required and filled capacity.
- Shift status.
- Recurring-shift information when applicable.

### Calendar Views

The calendar supports:

- Month view.
- Week view.
- Day view.

Use the view switcher to change how shifts are displayed.

### Calendar Filters

You can filter available shifts by:

- Search text for shift, pantry, or role.
- Pantry.
- Time bucket.

Use `Clear Filters` to return to the default view.

### Signing Up From the Calendar

Steps:

1. Open the `Calendar` tab.
2. Find a shift using the calendar or filters.
3. Open the shift details.
4. Review the pantry, time, and available roles.
5. Choose an open role.
6. Select the signup action.
7. Wait for the success message.

After signup, the shift appears in `My Shifts`.

Signup restrictions:

- You must be logged in as a volunteer.
- You can only sign yourself up.
- You cannot sign up for cancelled shifts.
- You cannot sign up for ended shifts.
- You cannot sign up for overlapping active shifts.
- You may be rate-limited if you sign up for too many shifts in a 24-hour period.
- A role may become full before your signup completes.

## 6. My Shifts Tab

The My Shifts tab shows your registered shifts.

### Views

You can switch between:

- Calendar view.
- List view.

Calendar view is useful for date-based planning. List view is useful for searching and reviewing status.

### List Filters

The list view supports:

- Search by shift, pantry, or role.
- Pantry filter.
- Time filter.
- Status filter.
- Sort order.

Use `Clear Filters` to reset the list.

### Signup Statuses

Common signup statuses:

- `CONFIRMED`: you are registered for the shift.
- `PENDING_CONFIRMATION`: the shift changed and you must reconfirm.
- `WAITLISTED`: the role could not be reconfirmed because capacity became unavailable.
- `SHOW_UP`: attendance was marked as present.
- `NO_SHOW`: attendance was marked as absent.

### Cancelling a Signup

Steps:

1. Open `My Shifts`.
2. Find the signup.
3. Select the cancel action.
4. Confirm the cancellation prompt.
5. Wait for the success message.

Cancellation removes the signup from your active commitments. If Google Calendar sync is connected, the linked calendar event is removed when possible.

### Reconfirming a Shift

You may need to reconfirm when a pantry lead or admin changes a shift's time, status, role, or capacity.

Steps:

1. Open `My Shifts`.
2. Find the shift marked `PENDING_CONFIRMATION`.
3. Review the changed shift details.
4. Choose to confirm or cancel.
5. Confirm the browser prompt.
6. Wait for the result message.

Possible outcomes:

- Reconfirmed successfully: your signup returns to `CONFIRMED`.
- Role full or unavailable: the role no longer has capacity.
- Reservation expired: the reconfirmation window passed or the shift started.
- Cancelled: your signup is removed.

Pending signups reserve capacity only for a limited window. If the window expires, sign up again if a role is still available.

## 7. Pantry Directory Tab

The Pantry Directory helps volunteers browse pantry locations and choose which pantries they want updates from.

### Browsing Pantries

You can:

- Search by pantry name or address.
- Sort the pantry list.
- Filter by subscription status.
- Select a pantry to view details.
- Preview upcoming shifts for a pantry.

### Subscribing to Pantry Updates

Steps:

1. Open the `Pantries` tab.
2. Select a pantry.
3. Choose the subscribe action.
4. Wait for the success message.

When subscribed, you can receive new-shift emails for that pantry if email notifications are configured.

### Unsubscribing

Steps:

1. Open the `Pantries` tab.
2. Select a subscribed pantry.
3. Choose the unsubscribe action.
4. Wait for the success message.

Unsubscribing stops new-shift subscription emails for that pantry. It does not cancel any existing shift signups.

## 8. My Account Tab

The My Account tab is where users manage profile details, email, calendar sync, and account deletion.

### Account Summary

The account summary can show:

- Name.
- Email.
- Phone number.
- Role.
- Timezone.
- Attendance or credibility information.
- Upcoming registered shift summary.

Times on the web are shown in your browser timezone.

### Updating Basic Information

Steps:

1. Open `My Account`.
2. Go to `Basic Information`.
3. Update full name or phone number.
4. Select `Save Basic Information`.
5. Wait for the success message.

Full name is required. Phone number can be blank unless required by the signup flow.

### Timezone Behavior

The app detects your browser timezone and sends it to the backend on API requests.

Timezone is used for:

- Displaying web times in your browser timezone.
- Saving your preferred timezone to your profile.
- Formatting notification email shift times.

If no timezone is saved, notification emails fall back to `America/New_York`.

### Changing Email Address

Email-change support depends on auth mode.

In Firebase mode:

1. Open `My Account`.
2. Go to `Email Address`.
3. Enter the new email.
4. Select `Start Email Change`.
5. Reauthenticate with Google when prompted.
6. Follow Firebase verification steps.
7. Log out and sign back in after verification.

In memory auth mode or unsupported account states, email changes may be unavailable.

### Connecting Google Calendar Sync

Google Calendar sync is optional and available only when:

- You are using a Google/Firebase-backed account.
- The server has Google OAuth configured.

Steps:

1. Open `My Account`.
2. Go to `Calendar Sync`.
3. Select `Connect Google Calendar`.
4. Complete the Google OAuth popup.
5. Return to the dashboard.
6. Confirm the status says sync is active.

When connected:

- New signups create Google Calendar events.
- Signup updates can update existing events.
- Signup cancellations remove events.
- Reconfirmed shifts update events.
- Waitlisted, expired, or deleted signups remove events when possible.

### Disconnecting Google Calendar Sync

Steps:

1. Open `My Account`.
2. Go to `Calendar Sync`.
3. Select `Disconnect Auto Sync`.
4. Confirm the prompt.
5. Wait for the success message.

Disconnecting removes existing synced events from Google Calendar when possible and deletes the app's stored Google Calendar connection.

### Deleting Your Account

Steps:

1. Open `My Account`.
2. Go to `Delete Account`.
3. Select `Delete My Account`.
4. Confirm the permanent deletion prompt.
5. In Firebase mode, reauthenticate with Google if prompted.

Deletion removes your local app account and signs you out. In Firebase mode, it also deletes the linked Firebase account after fresh Google reauthentication.

The protected super admin account cannot delete itself.

## 9. Manage Shifts Tab

The Manage Shifts tab is for pantry leads, admins, and super admins.

Pantry leads see and manage assigned pantries. Admin-capable users can manage all pantries.

### Selecting a Pantry

If the pantry selector is visible:

1. Choose a pantry from the dropdown.
2. The shift list refreshes for that pantry.
3. The create and management panels use the selected pantry.

If no pantry is selected, shift creation and listing may be unavailable.

### Shift Queue

The shift queue can be filtered by:

- Incoming.
- Ongoing.
- Past.
- Cancelled.
- Search text.

Select a shift from the queue to inspect details and registrations.

### Creating a One-Time Shift

Steps:

1. Open `Manage Shifts`.
2. Select a pantry if needed.
3. Select `Create Shift`.
4. Enter the shift name.
5. Enter start date and time.
6. Enter end date and time.
7. Add at least one role or position.
8. For each role, enter a role title and required count.
9. Select `Create Shift with Roles`.
10. Wait for the success message.

Each role must have:

- A non-empty title.
- Required count of at least 1.

If pantry subscribers exist and email is configured, they may receive a new-shift notification.

### Creating a Recurring Shift

Steps:

1. Start a normal shift creation.
2. Turn on `Repeat`.
3. Set the interval in weeks.
4. Select weekdays.
5. Choose an end rule:
   - A fixed number of occurrences.
   - An until date.
6. Add roles.
7. Select `Create Shift with Roles`.

Recurring shifts create individual shift occurrences linked to the same recurring series.

Notes:

- The app currently supports weekly recurrence.
- Recurring shifts must have a finite end rule.
- The starting weekday is included automatically when applicable.
- The system caps the number of generated occurrences.

### Viewing Shift Details

Select a shift from the queue to view:

- Shift name.
- Pantry.
- Time window.
- Status.
- Recurring-series information.
- Role coverage.
- Registration details.
- Available management actions.

### Viewing Registrations

Steps:

1. Open `Manage Shifts`.
2. Select a shift.
3. Use the registrations or details area.
4. Review volunteers by role.

Registration details can include:

- Volunteer name.
- Email.
- Phone number.
- Signup status.
- Role.
- Pending reconfirmation count.

### Editing a Shift

Steps:

1. Open `Manage Shifts`.
2. Select a shift.
3. Choose the edit action.
4. Update shift name, time, status, recurrence settings, or roles.
5. Select `Save Shift Changes`.
6. If the shift is recurring, choose whether to apply to:
   - This event only.
   - This and following events.
7. Wait for the success message.

Important behavior:

- Ended shifts are locked and cannot be edited.
- Reducing capacity or changing shift details can move existing signups to `PENDING_CONFIRMATION`.
- Affected volunteers may receive update emails.
- Volunteers must reconfirm to keep their slot.

### Cancelling a Shift

Steps:

1. Open `Manage Shifts`.
2. Select a shift.
3. Choose the cancel action.
4. If the shift is recurring, choose whether to cancel only this event or this and following events.
5. Confirm the prompt.
6. Wait for the success message.

Cancelling a shift prevents new signups and may notify affected volunteers.

### Reopening or Revoking Cancellation

If the UI offers a revoke or reopen action for a cancelled shift:

1. Select the cancelled shift.
2. Choose the revoke action.
3. Confirm the prompt.
4. Wait for the success message.

Previously signed-up volunteers may remain pending until they reconfirm.

### Managing Roles

During create or edit, each role represents a volunteer position needed for that shift.

Examples:

- Food Distribution.
- Check In.
- Sorting.
- Packing.
- Driver.

Rules:

- A shift must include at least one role for full creation.
- Required count must be at least 1.
- Removing or reducing a role with existing signups can require volunteer reconfirmation.
- Cancelled roles do not accept new signups.

### Sending a Help Broadcast

Help broadcasts contact selected volunteers when a shift needs more coverage.

Steps:

1. Open `Manage Shifts`.
2. Select the shift that needs help.
3. Choose `Broadcast Help`.
4. Review suggested volunteers.
5. Search by name or email if needed.
6. Select up to 25 volunteers.
7. Select `Send Broadcast`.
8. Wait for the result message.

Rules:

- You must be allowed to manage the shift.
- You cannot send broadcasts for ended shifts.
- You cannot send broadcasts for cancelled shifts.
- There is a per-sender cooldown.
- Recipients must be existing volunteers.

### Taking Attendance

Attendance can be marked by pantry leads for their pantries and by admin-capable users.

Steps:

1. Open `Manage Shifts`.
2. Select the shift.
3. Choose `Take Attendance`.
4. Search registrants if needed.
5. Mark each volunteer as `SHOW_UP` or `NO_SHOW`.
6. Close the modal when finished.

Attendance window:

- Opens 15 minutes before shift start.
- Closes 6 hours after shift end.

Attendance updates the volunteer's attendance score.

## 10. Admin Panel

The Admin Panel has two main subtabs:

- `Manage Pantries`.
- `Manage Users`.

Only admin-capable users can use the Admin Panel.

## 11. Admin: Manage Pantries

### Creating a Pantry

Steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. In `Create Pantry`, enter pantry name.
4. Enter pantry address.
5. Select `Create Pantry`.
6. Wait for the success message.

The new pantry becomes available for shift management and volunteer browsing.

### Searching Pantries

Use the pantry search field to filter by:

- Pantry name.
- Pantry address.

Select a pantry to view and manage its assigned leads.

### Editing a Pantry

Steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. Find the pantry.
4. Choose the edit action.
5. Update name or address.
6. Save.
7. Wait for the success message.

### Deleting a Pantry

Steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. Find the pantry.
4. Choose the delete action.
5. Confirm the deletion prompt.

Deleting a pantry removes its dependent shifts, roles, signups, subscriptions, and lead assignments.

Use this action carefully.

### Assigning Pantry Leads

Before a user can be assigned as a pantry lead, that user must have the `PANTRY_LEAD` role.

Steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. Select a pantry.
4. Search eligible pantry lead users.
5. Select the lead.
6. Add the lead to the pantry.
7. Wait for the success message.

### Removing Pantry Leads

Steps:

1. Open `Admin Panel`.
2. Select `Manage Pantries`.
3. Select a pantry.
4. Find the assigned lead.
5. Choose remove.
6. Confirm the prompt.
7. Wait for the success message.

Removing a pantry lead only removes their assignment to that pantry. It does not delete the user account.

## 12. Admin: Manage Users

### Searching Users

Steps:

1. Open `Admin Panel`.
2. Select `Manage Users`.
3. Search by full name or email.
4. Optionally filter by role.
5. Select `Search Users`.

The results table lists matching users.

### Viewing a User Profile

Steps:

1. Search for users.
2. Select a user from the results.
3. Review the profile panel.

The profile can show:

- Basic user identity.
- Email.
- Phone number.
- Roles.
- Attendance score.
- Signup history.

### Updating User Roles

Steps:

1. Open a user profile.
2. Select exactly one editable role.
3. Save the role change.
4. Wait for the success message.

Restrictions:

- Users can have only one editable role through this admin flow.
- The protected super admin account cannot be edited.
- `SUPER_ADMIN` cannot be assigned through this endpoint.
- Only a super admin can remove `ADMIN` from another admin.

## 13. Public Pages

The app includes public pages that do not require login:

- `/`: homepage.
- `/privacy`: privacy policy.
- `/terms`: terms page.
- `/term`: alternate terms route.

Public API endpoints can list pantries and public shifts:

- `/api/public/pantries`
- `/api/public/pantries/{slug}/shifts`

Public pages support product discovery and Google OAuth verification.

## 14. Notifications

The app can send email notifications when Resend is configured.

Notification types:

- Signup confirmation.
- Shift update requiring reconfirmation.
- Shift cancellation.
- New one-time shift for pantry subscribers.
- New recurring shift series for pantry subscribers.
- Help broadcast for selected volunteers.

Notifications are side effects. If an email provider is unavailable, the shift or signup action may still complete in the app.

## 15. Common Messages and What They Mean

### Authentication required

Your session is missing or expired.

What to do:

- Log in again.
- Refresh the page if you recently logged in.

### Forbidden

Your account does not have permission for the action.

What to do:

- Confirm you are using the correct account.
- Ask an admin to check your role or pantry lead assignment.

### Not a lead for this pantry

You have a pantry lead role but are not assigned to that specific pantry.

What to do:

- Ask an admin to assign you as a lead for that pantry.

### Shift has ended

The shift is in the past and no longer accepts signups or edits.

What to do:

- Choose a future shift.
- For attendance, verify you are inside the allowed attendance window.

### Past shift locked

The app prevents edits to ended shifts.

What to do:

- Manage only upcoming or currently allowed shifts.

### Already signed up

You already have a signup for that role.

What to do:

- Check `My Shifts`.
- Cancel your existing signup before choosing another role if needed.

### Can't register for overlapping shift

You are already signed up for another active shift that overlaps this time.

What to do:

- Pick a different time.
- Cancel the conflicting signup first if appropriate.

### Signup rate limited

You signed up for too many shifts in a rolling 24-hour window.

What to do:

- Wait until the cooldown time shown in the message.

### Role full or unavailable

The role has no remaining capacity or is not available.

What to do:

- Pick another role or shift.
- If reconfirming, cancel or choose a new available shift.

### Reservation expired

Your pending reconfirmation window expired.

What to do:

- Sign up again if slots are still available.

### Google Calendar unavailable

The server is missing Google OAuth setup or your account is not eligible for Calendar sync.

What to do:

- Use a Google/Firebase login.
- Ask an administrator to confirm Google OAuth configuration.

## 16. Best Practices

### For Volunteers

- Keep your phone number and email current.
- Check `My Shifts` after signing up.
- Reconfirm promptly when a shift changes.
- Cancel early if you can no longer attend.
- Connect Google Calendar if available and useful.
- Subscribe only to pantries where you want new-shift updates.

### For Pantry Leads

- Create shifts early enough for volunteers to plan.
- Use clear shift names and role titles.
- Set realistic required counts.
- Review registrations before the shift starts.
- Use help broadcasts only when extra coverage is needed.
- Mark attendance within the attendance window.
- Be careful when reducing role capacity because volunteers may need to reconfirm.

### For Admins

- Assign pantry leads only to the pantries they should manage.
- Keep user roles simple and intentional.
- Avoid deleting pantries unless the data should really be removed.
- Verify notification and Google Calendar settings before relying on them operationally.
- Preserve access to the protected super admin account.

## 17. Quick Task Reference

| Task                        | Where To Go   | Role Needed                             |
| --------------------------- | ------------- | --------------------------------------- |
| Browse available shifts     | Calendar      | Logged-in user                          |
| Sign up for a shift         | Calendar      | Volunteer                               |
| Cancel your signup          | My Shifts     | Signup owner or admin                   |
| Reconfirm changed shift     | My Shifts     | Signup owner or admin                   |
| Subscribe to pantry updates | Pantries      | Volunteer                               |
| Update profile              | My Account    | Logged-in user                          |
| Connect Google Calendar     | My Account    | Google/Firebase user                    |
| Create shift                | Manage Shifts | Pantry lead for pantry or admin         |
| Create recurring shift      | Manage Shifts | Pantry lead for pantry or admin         |
| Edit shift                  | Manage Shifts | Pantry lead for pantry or admin         |
| Cancel shift                | Manage Shifts | Pantry lead for pantry or admin         |
| Send help broadcast         | Manage Shifts | Pantry lead for pantry or admin         |
| Mark attendance             | Manage Shifts | Pantry lead for pantry or admin         |
| Create pantry               | Admin Panel   | Admin or super admin                    |
| Assign pantry lead          | Admin Panel   | Admin or super admin                    |
| Search users                | Admin Panel   | Admin or super admin                    |
| Change user role            | Admin Panel   | Admin or super admin, with restrictions |

## 18. Support Checklist

When reporting a problem, include:

- The tab or screen you were using.
- The action you tried.
- The exact error message.
- Your role.
- The pantry name, if relevant.
- The shift name and time, if relevant.
- Whether you were using Google login or demo login.
- Whether Google Calendar sync was connected.

This helps admins or developers identify whether the issue is permissions, configuration, shift state, capacity, or an external integration.
