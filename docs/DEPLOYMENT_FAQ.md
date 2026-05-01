# DigitalOcean Deployment FAQ

This document summarizes the full DigitalOcean deployment journey for the Volunteer Management System, including what was set up, the issues that appeared, how they were diagnosed, and how they were fixed.

Use this as the first troubleshooting reference for future deploys.

---

## 1. What was deployed?

The app is deployed to **DigitalOcean App Platform** as:

- one Python web service
- one managed MySQL database
- one pre-deploy job for demo database bootstrap/reset behavior

Production domain:

- `https://app.vmswedenison.site`

CI/CD:

- GitHub Actions runs tests
- GitHub Actions deploys App Platform from `.do/app.yaml`

---

## 2. What did I set up in the repo?

These deployment-related files were added or updated:

- `.do/app.yaml`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `docs/DEPLOY_DIGITALOCEAN.md`
- root `requirements.txt`
- root `runtime.txt`
- `backend/db/demo_bootstrap.py`
- `tests/test_demo_bootstrap.py`

Key runtime changes:

- Flask now has `/healthz`
- production cookie and proxy settings are env-driven
- Firebase Admin credentials can be loaded from a raw JSON secret
- App Platform uses Gunicorn in production

---

## 3. What did the user already do in DigitalOcean and GitHub?

The following platform work was completed during setup:

- created a DigitalOcean Managed MySQL cluster:
  - `db-mysql-nyc3-vmswedenison-35947`
- added GitHub Actions variables and secrets
  - triggered deploys from `main`
- the App Platform app is automatically created and updated from `.do/app.yaml` on deploy
- configured custom domain:
  - `app.vmswedenison.site`


---

## 4. Why did App Platform initially fail to detect the app?

### Problem

App Platform buildpack detection failed with a message similar to:

> could not detect app files that match known buildpacks

### Cause

The App Platform service was building from repo root, but the repo originally only had:

- `backend/requirements.txt`

DigitalOcean’s Python buildpack detects Python apps only if the source directory root contains one of:

- `requirements.txt`
- `Pipfile`
- `setup.py`

### Fix

Added two files at repo root:

- `requirements.txt`
  - contains `-r backend/requirements.txt`
- `runtime.txt`
  - pins Python to `python-3.12.12`

Also removed the custom `build_command` from `.do/app.yaml` so App Platform can use standard Python buildpack behavior.

---

## 5. Why did the GitHub deploy action fail with `input "token" is required`?

### Problem

GitHub Actions deploy failed before talking to DigitalOcean.

### Cause

`DIGITALOCEAN_ACCESS_TOKEN` had been added as an **environment secret**, but the workflow did not declare a GitHub Actions environment. That made the secret unavailable to:

- `${{ secrets.DIGITALOCEAN_ACCESS_TOKEN }}`

### Fix

Move the deployment values to:

- **Repository secrets**
- **Repository variables**

Required repository secrets:

- `DIGITALOCEAN_ACCESS_TOKEN`
- `FLASK_SECRET_KEY`
- `FIREBASE_ADMIN_CREDENTIALS_JSON`
- `RESEND_API_KEY`

Required repository variables:

- `DIGITALOCEAN_DB_CLUSTER_NAME`
- `FIREBASE_API_KEY`
- `FIREBASE_AUTH_DOMAIN`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_APP_ID`
- `RESEND_FROM_EMAIL`

---

## 6. Why did the app spec fail to parse?

### Problem

The deploy action failed while parsing `.do/app.yaml`.

### Causes and fixes

#### A. Placeholder values were unquoted

App spec placeholders like:

```yaml
value: ${RESEND_API_KEY}
```

caused parsing issues.

Fix:

```yaml
value: "${RESEND_API_KEY}"
```

#### B. Firebase JSON secret broke YAML parsing

This line caused another parse failure:

```yaml
value: "${FIREBASE_ADMIN_CREDENTIALS_JSON}"
```

because the substituted Firebase JSON contains many double quotes.

Fix:

```yaml
value: '${FIREBASE_ADMIN_CREDENTIALS_JSON}'
```

This keeps the substituted one-line JSON valid inside YAML.

#### C. Firebase secret had to be one-line JSON

The Firebase Admin SDK JSON secret could not be stored as pretty-printed multi-line JSON in GitHub.

Fix:

- convert the Firebase JSON to one line
- preserve `\n` inside the private key string
- store that one-line JSON in:
  - `FIREBASE_ADMIN_CREDENTIALS_JSON`

---

## 7. Why did the site say `connection refused` even though deployment succeeded?

### Problem

The app was healthy in DigitalOcean logs, but the browser showed:

- `ERR_CONNECTION_REFUSED`

### Cause

The custom domain was pointing at a private IP:

- `10.143.222.115`

That IP is not a public ingress target for App Platform.

### Fix

Update DNS to use the values DigitalOcean gives on the App Platform domain instructions page:

- the `ondigitalocean.app` CNAME target
- or the public App Platform A records for apex domains if needed

Do **not** point the public domain to an internal/private IP.

---

## 8. Why did users log in but show no roles?

### Problem

Login worked, but users had no roles and the role-based UI did not appear.

### Cause

This was not a DB connectivity failure.

Production was configured with:

- `SEED_MYSQL_FROM_JSON_ON_EMPTY=false`

So the app created the schema but did not load demo seed data. That left tables like `roles` empty.

When Firebase signup tried to create a new user with:

- `roles=["VOLUNTEER"]`

the backend silently skipped role assignment because `VOLUNTEER` did not exist in the `roles` table yet.

### Fix

Implemented a dedicated demo bootstrap flow as a pre-deploy job so demo data is controlled by deployment, not by normal web-app startup.

---

## 9. How does the current demo database bootstrap work?

The deployment now includes a **PRE_DEPLOY job**:

- `demo-bootstrap`

It runs:

```bash
PYTHONPATH=/workspace/backend python -m db.demo_bootstrap
```

The bootstrap script:

1. computes a SHA-256 schema signature from all files in:
   - `backend/db/migrations/*.sql`
2. reads the previously stored schema signature from:
   - `app_bootstrap_state`
3. decides what to do:
   - if no previous signature exists: reset all app tables and seed demo data
   - if signature is unchanged: do nothing
   - if signature changed: reset all app tables and seed demo data again

This behavior is controlled by:

- `DEMO_DB_BOOTSTRAP_MODE=reset_if_untracked_or_schema_changed`

The web app itself has:

- `DEMO_DB_BOOTSTRAP_MODE=disabled`

so the web service never wipes or reseeds the DB during normal restarts.

---

## 10. What tables are reset by the demo bootstrap?

When a reset is needed, the bootstrap drops these app tables:

- `shift_signups`
- `shift_roles`
- `shifts`
- `shift_series`
- `pantry_subscriptions`
- `pantry_leads`
- `pantries`
- `user_roles`
- `users`
- `roles`

Then it:

- reruns schema initialization
- reseeds `backend/data/mysql.json`
- updates the stored schema signature

The metadata table `app_bootstrap_state` is kept and reused to track schema history.

---

## 11. Why did the pre-deploy bootstrap job fail with `No module named 'db'`?

### Problem

The App Platform job could not import:

- `db.init_schema`

### Cause

The bootstrap script was being executed from repo root without `backend/` on Python’s import path.

### Fix

The bootstrap script now prepends `backend/` to `sys.path` at startup.

---

## 12. Why did the pre-deploy bootstrap job fail with `No module named 'mysql.connector'; 'mysql' is not a package`?

### Problem

The pre-deploy job tried to import the MySQL connector and failed with an import-path collision.

### Cause

The script was run as:

```bash
python backend/db/demo_bootstrap.py
```

That made Python treat `backend/db` as the first import location, so the local file:

- `backend/db/mysql.py`

shadowed the real third-party package:

- `mysql.connector`

### Fix

Changed the pre-deploy job command to run the bootstrap as a module:

```bash
PYTHONPATH=/workspace/backend python -m db.demo_bootstrap
```

That avoids the shadowing issue cleanly.

---

## 13. What is the current expected deploy behavior?

On every deploy:

1. GitHub Actions runs tests
2. GitHub Actions deploys the App Platform spec
3. App Platform runs the `demo-bootstrap` PRE_DEPLOY job
4. The bootstrap job checks schema signature
5. It either:
   - exits without DB changes
   - or resets and reseeds demo data
6. After the job succeeds, the web service deploys

---

## 14. What should happen on the next deploy?

Because the new bootstrap tracking table may not exist yet in production, the next deploy should:

- treat the DB as untracked
- reset app tables
- seed `backend/data/mysql.json`

After that:

- roles should exist
- seeded admin/login demo data should exist
- future deploys should leave data alone until the schema changes

---

## 15. How do I verify the app after deploy?

Check these in order:

1. App health:
   - `https://app.vmswedenison.site/healthz`
2. Public homepage loads without login and links to the privacy policy:
   - `https://app.vmswedenison.site/`
3. Privacy policy loads without login:
   - `https://app.vmswedenison.site/privacy`
4. Dashboard loads:
   - `https://app.vmswedenison.site/dashboard`
5. Roles endpoint returns seeded roles:
   - `/api/roles`
6. Login with the seeded admin/demo Google account
7. Confirm role-based UI appears
8. Confirm demo pantries, shifts, and users exist
9. Confirm a second deploy with no migration changes does not wipe data

For Google OAuth verification, do not submit an `ondigitalocean.app` URL as the homepage. Submit the custom domain homepage and privacy policy after the domain is verified in Google Search Console:

- Authorized domain: `vmswedenison.site`
- Homepage: `https://app.vmswedenison.site/`
- Privacy policy: `https://app.vmswedenison.site/privacy`
- Terms: `https://app.vmswedenison.site/terms`
- Calendar OAuth redirect: `https://app.vmswedenison.site/google-calendar/oauth/callback`

---

## 16. How should GoDaddy, DigitalOcean, Firebase, and Google use the `app` subdomain?

Use `app.vmswedenison.site` as the deployed app URL.

In GoDaddy DNS, add the CNAME record at the authoritative DNS provider for `vmswedenison.site`:

```text
Type: CNAME
Name: app
Data: vmswedenison-prod-mtip8.ondigitalocean.app.
TTL: 1 Hour
```

In DigitalOcean App Platform, attach this exact domain:

```text
app.vmswedenison.site
```

In Firebase Auth, add this authorized domain:

```text
app.vmswedenison.site
```

In Google Auth Platform / OAuth consent, use:

```text
Authorized domain: vmswedenison.site
Homepage URL: https://app.vmswedenison.site/
Privacy policy URL: https://app.vmswedenison.site/privacy
Terms URL: https://app.vmswedenison.site/terms
```

In the Google OAuth Web Application client, add this authorized redirect URI:

```text
https://app.vmswedenison.site/google-calendar/oauth/callback
```

In GitHub repository variables/secrets:

```env
# Variables
GOOGLE_OAUTH_CLIENT_ID=<web OAuth client id>
GOOGLE_OAUTH_REDIRECT_URI=https://app.vmswedenison.site/google-calendar/oauth/callback

# Secret
GOOGLE_OAUTH_CLIENT_SECRET=<web OAuth client secret>
```

If Google OAuth request details still show `redirect_uri=http://localhost:5000/google-calendar/oauth/callback`, the production app is still using the local variable. Update the GitHub repository variable, make sure the deploy workflow passes it to DigitalOcean, and redeploy.

---

## 17. Why do I see Cloudflare 1001, TLS errors, or 404 on the custom domain?

These usually mean the domain is not fully attached yet.

- Cloudflare `Error 1001 DNS resolution error`: add the CNAME in the DNS provider that is actually authoritative for `vmswedenison.site`. If the domain uses Cloudflare nameservers, adding the record only in GoDaddy will not affect DNS.
- `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`: wait for DigitalOcean to issue the certificate for `app.vmswedenison.site`. If using Cloudflare, keep the record DNS-only until DigitalOcean shows the certificate as active.
- `HTTP ERROR 404`: DNS is reaching DigitalOcean, but the App Platform app does not have `app.vmswedenison.site` attached, or the latest `.do/app.yaml` has not been deployed.

---

## 18. Why does Google still show "Google hasn't verified this app"?

Branding approval is not the same as sensitive-scope verification. Calendar sync requests `https://www.googleapis.com/auth/calendar.events`, which Google treats as user-data access. In **Google Auth Platform -> Data access**, complete the missing fields for the Calendar scope:

- scope justification
- demo video

Use a justification like:

```text
Volunteer Management uses Google Calendar access only when a signed-in user opts in to Calendar Sync. The app creates, updates, and deletes calendar events for that user's volunteer shift signups so their personal calendar matches their active volunteer commitments. The app does not read unrelated calendar events and stores only the OAuth tokens needed for sync plus the Google event IDs linked to local signup records.
```

The demo video should show the complete production flow:

1. Open `https://app.vmswedenison.site/`.
2. Sign in with Firebase/Google.
3. Open `/dashboard` and the account Calendar Sync setting.
4. Click connect and show the Google OAuth consent screen in English.
5. Approve the scope.
6. Create or confirm a volunteer signup.
7. Show the event created or updated in Google Calendar.
8. Disconnect Calendar Sync and show synced events are removed.

---

## 19. What should I do if deploy fails again?

Check failures in this order:

1. GitHub Actions `Deploy Production` logs
2. DigitalOcean App Platform deploy logs
3. DigitalOcean pre-deploy job logs for `demo-bootstrap`
4. DNS configuration for `app.vmswedenison.site`
5. GitHub repository secret/variable names

When debugging, always copy:

- the exact error
- the relevant log lines above it
- whether the failure is in:
  - GitHub Actions
  - App Platform build
  - PRE_DEPLOY job
  - runtime web logs

---

## 17. What are the important deployment files now?

- [app.yaml](/Users/dohoanggiahuy/Desktop/volunteer_managing/.do/app.yaml)
- [deploy.yml](/Users/dohoanggiahuy/Desktop/volunteer_managing/.github/workflows/deploy.yml)
- [DEPLOY_DIGITALOCEAN.md](/Users/dohoanggiahuy/Desktop/volunteer_managing/docs/DEPLOY_DIGITALOCEAN.md)
- [demo_bootstrap.py](/Users/dohoanggiahuy/Desktop/volunteer_managing/backend/db/demo_bootstrap.py)

---

## 18. Short version: what finally made the deployment work?

The deployment became stable after all of these were fixed:

- App Platform secrets moved to repository scope
- app spec placeholders were quoted correctly
- Firebase Admin secret was stored as one-line JSON
- Firebase JSON placeholder used single quotes in YAML
- root `requirements.txt` and `runtime.txt` were added for buildpack detection
- domain DNS was corrected to use DigitalOcean public ingress
- demo DB initialization was moved into a pre-deploy job
- the pre-deploy job was changed to run as a Python module instead of a file path

That is the baseline deployment shape to keep going forward.
