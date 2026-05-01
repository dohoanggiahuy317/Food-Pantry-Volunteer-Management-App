# Deploy to DigitalOcean App Platform

This repository now includes the production deployment artifacts for:

- DigitalOcean App Platform web service
- DigitalOcean Managed MySQL
- GitHub Actions CI/CD
- Production app domain `https://app.vmswedenison.site`

## 1. Create the Managed MySQL Cluster

Create a production MySQL cluster in the `nyc` region before the first deployment.

Recommended settings:

- Engine: MySQL 8
- Cluster name: choose a stable name such as `vmswedenison-mysql`
- Database name: `volunteer_managing`
- Database user: `volunteer_app`

After the cluster exists, keep the exact cluster name. The App Platform spec references it through the GitHub variable `DIGITALOCEAN_DB_CLUSTER_NAME`.

## 2. Configure GitHub Variables and Secrets

Add these repository variables in GitHub:

- `DIGITALOCEAN_DB_CLUSTER_NAME`
- `FIREBASE_API_KEY`
- `FIREBASE_AUTH_DOMAIN`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_APP_ID`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `RESEND_FROM_EMAIL`

Example production Google OAuth values:

```env
GOOGLE_OAUTH_CLIENT_ID=<web OAuth client id>
GOOGLE_OAUTH_REDIRECT_URI=https://app.vmswedenison.site/google-calendar/oauth/callback
```

Add these repository secrets in GitHub:

- `DIGITALOCEAN_ACCESS_TOKEN`
- `FLASK_SECRET_KEY`
- `FIREBASE_ADMIN_CREDENTIALS_JSON`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `RESEND_API_KEY`

Notes:

- `FIREBASE_ADMIN_CREDENTIALS_JSON` should be the full Firebase Admin SDK JSON document as one secret value.
- `FLASK_SECRET_KEY` should be a long random string.
- `DIGITALOCEAN_ACCESS_TOKEN` needs write access to App Platform.

## 3. Review the App Platform Spec

The production spec lives at [app.yaml](/Users/dohoanggiahuy/Desktop/volunteer_managing/.do/app.yaml).

Important details:

- The service builds from the repository root, not `backend/`, because Flask serves sibling `frontend/` assets at runtime.
- The service runs with Gunicorn on port `8080`.
- A pre-deploy App Platform job now owns demo DB bootstrapping and reseeding behavior.
- `/healthz` is used for App Platform health checks.
- `/` serves the public OAuth-verification homepage, `/privacy` serves the public privacy policy, and `/dashboard` serves the authenticated app.
- Production seeding is disabled with `SEED_MYSQL_FROM_JSON_ON_EMPTY=false`.
- MySQL connection settings come from App Platform bindable variables for the attached managed database.

## Demo Database Bootstrap Behavior

The app spec now includes a `PRE_DEPLOY` job that manages demo data in MySQL.

Behavior:

- If the schema hash has never been recorded, the job drops all app tables, recreates the schema, and seeds `backend/data/mysql.json`.
- If the schema hash matches the last deployed schema hash, the job exits without changing data.
- If the schema hash changes, the job drops all app tables, recreates the schema, and reseeds the demo dataset.

The schema hash is derived from all files in `backend/db/migrations/*.sql`.

Environment variables:

- Web service: `DEMO_DB_BOOTSTRAP_MODE=disabled`
- Pre-deploy job: `DEMO_DB_BOOTSTRAP_MODE=reset_if_untracked_or_schema_changed`

## 4. Create the App Platform App

You can let the first GitHub Actions deploy create the app from `.do/app.yaml`, or create it in the DigitalOcean control panel first.

If creating it manually:

1. Connect the GitHub repository.
2. Use the existing app spec in `.do/app.yaml`.
3. Set the app name to `vmswedenison-prod`.
4. Confirm the region is `nyc`.
5. Confirm the attached database is the managed cluster you created.

## 5. Configure the Domain

Add `app.vmswedenison.site` as the primary domain in App Platform.

In DigitalOcean App Platform, choose the option where you manage DNS yourself, then copy the CNAME target that DigitalOcean gives you. In GoDaddy DNS, create this record:

| Type  | Name | Data / Value |
| ----- | ---- | ------------ |
| CNAME | `app` | the exact DigitalOcean `*.ondigitalocean.app` target |

If DigitalOcean tells you to point to `vmswedenison-prod-mtip8.ondigitalocean.app`, the GoDaddy record is:

```text
Type: CNAME
Name: app
Data: vmswedenison-prod-mtip8.ondigitalocean.app.
TTL: 1 Hour
```

This makes the app URL `https://app.vmswedenison.site`. The top private domain remains `vmswedenison.site`, which is what Google Search Console and Google OAuth authorized domains use.

Wait for:

- DNS propagation
- TLS certificate issuance

After the app is live, verify:

- `https://app.vmswedenison.site/healthz`
- `https://app.vmswedenison.site/`
- `https://app.vmswedenison.site/privacy`
- `https://app.vmswedenison.site/dashboard`

For Google OAuth verification, use a custom domain you control. Do not submit the default `ondigitalocean.app` URL as the OAuth homepage because Google requires ownership of the homepage domain.

Common DNS/TLS symptoms:

- Cloudflare `Error 1001 DNS resolution error`: `app.vmswedenison.site` is not resolving through the active DNS provider yet, or the DNS record was added somewhere other than the authoritative nameserver. Check whether GoDaddy or Cloudflare is authoritative for `vmswedenison.site`, then add the CNAME there.
- `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`: DNS is reaching an endpoint before DigitalOcean has issued/attached the certificate, or the domain is proxied through Cloudflare before the DigitalOcean certificate is ready. Wait for DigitalOcean domain status to be active and certificate-ready. If using Cloudflare, use DNS-only mode until DigitalOcean TLS is active.
- `HTTP ERROR 404` on `https://app.vmswedenison.site/`: DNS reached DigitalOcean, but the App Platform app does not have `app.vmswedenison.site` attached as a domain, or the latest app spec was not deployed.

## 6. Configure Firebase for Production

In Firebase:

1. Add `app.vmswedenison.site` to Authorized domains.
2. Confirm the production web app config matches the GitHub variables.
3. Generate or reuse a dedicated production Admin SDK credential.
4. Store the Admin SDK JSON in the GitHub secret `FIREBASE_ADMIN_CREDENTIALS_JSON`.

The backend now supports both:

- a local file path for development
- a raw JSON secret for production

## 7. Configure Resend

Set `RESEND_FROM_EMAIL` to the verified sender you want to use on your domain.

If you want to postpone email delivery, leave `RESEND_API_KEY` unset. The app will not crash, but notifications will be skipped and logged as configuration failures.

## 8. Configure Google Calendar OAuth

Google Calendar auto sync is optional, but production verification requires a custom domain and public legal pages.

In Google Cloud:

1. Enable the Google Calendar API.
2. Verify `vmswedenison.site` in Google Search Console. Prefer a Domain property so ownership covers `app.vmswedenison.site`.
3. Add `vmswedenison.site` under OAuth authorized domains. Do not add `app.vmswedenison.site` there; Google wants the top private domain.
4. Set the OAuth homepage URL to `https://app.vmswedenison.site/`.
5. Set the privacy policy URL to `https://app.vmswedenison.site/privacy`.
6. Set the terms URL to `https://app.vmswedenison.site/terms`. The app also serves `/term` as a compatibility alias, but use `/terms` in Google Console.
7. Add the OAuth redirect URI `https://app.vmswedenison.site/google-calendar/oauth/callback` to the OAuth Web Application client.

Production environment values must match the Google OAuth client exactly:

```env
GOOGLE_OAUTH_CLIENT_ID=<web OAuth client id>
GOOGLE_OAUTH_CLIENT_SECRET=<web OAuth client secret>
GOOGLE_OAUTH_REDIRECT_URI=https://app.vmswedenison.site/google-calendar/oauth/callback
CORS_ALLOWED_ORIGINS=https://app.vmswedenison.site
```

If Google shows `Error 403: access_denied` and the request details include `redirect_uri=http://localhost:5000/google-calendar/oauth/callback`, the deployed app is still using the local redirect URI. Fix `GOOGLE_OAUTH_REDIRECT_URI` in GitHub repository variables, confirm the workflow passes it to DigitalOcean, redeploy, and confirm the OAuth request uses `https://app.vmswedenison.site/google-calendar/oauth/callback`.

If Google still shows "Google hasn't verified this app" after branding is filled out, check **Google Auth Platform -> Data access**. Sensitive scopes need a scope justification and a demo video before verification is complete. This app requests `https://www.googleapis.com/auth/calendar.events`, so the justification should explain that Calendar access is used only to create, update, and delete volunteer signup events that the signed-in user opted to sync. The demo video should show login, Calendar Sync connect, the Google consent screen with the requested scopes, an event created/updated in Google Calendar, and disconnect/removal behavior.

Reference docs:

- [DigitalOcean App Platform custom domains](https://docs.digitalocean.com/products/app-platform/how-to/manage-domains/)
- [Google OAuth data access verification](https://support.google.com/cloud/answer/15549135)
- [Google OAuth demo video requirements](https://support.google.com/cloud/answer/13804565)

## 9. CI/CD Behavior

Two workflows are now committed:

- [ci.yml](/Users/dohoanggiahuy/Desktop/volunteer_managing/.github/workflows/ci.yml)
- [deploy.yml](/Users/dohoanggiahuy/Desktop/volunteer_managing/.github/workflows/deploy.yml)

Behavior:

- Pull requests into `main` run `pytest tests`
- Pushes to `main` run `pytest tests`
- Pushes to `main` also run a production deploy after tests pass

App Platform `deploy_on_push` is disabled in the spec so GitHub Actions remains the deployment gate.

## 10. First Release Smoke Test

After the first successful deployment:

1. Open `https://app.vmswedenison.site/`.
2. Confirm the public homepage loads without login and links to `/privacy`.
3. Open `https://app.vmswedenison.site/privacy` and confirm the privacy policy loads without login.
4. Open `https://app.vmswedenison.site/dashboard` and confirm the dashboard auth shell loads.
5. Complete Google sign-in through Firebase.
6. Confirm the app can read and write MySQL data.
7. Confirm session persistence works across page reloads over HTTPS.
8. If Google Calendar OAuth is configured, connect Calendar sync from My Account.
9. If Resend is enabled, trigger one notification flow and confirm delivery.

## 11. Ongoing Updates

For future releases:

1. Open a pull request into `main`.
2. Wait for CI to pass.
3. Merge to `main`.
4. GitHub Actions deploys the updated App Platform spec and code automatically.
