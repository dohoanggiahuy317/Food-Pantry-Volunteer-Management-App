# Deploy to DigitalOcean App Platform

This repository now includes the production deployment artifacts for:

- DigitalOcean App Platform web service
- DigitalOcean Managed MySQL
- GitHub Actions CI/CD
- Production domain `https://vmswedenison.site`

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
- `GOOGLE_OAUTH_CLIENT_ID=`
- `GOOGLE_OAUTH_REDIRECT_URI=https://vmswedenison.site/google-calendar/oauth/callback`


Add these repository secrets in GitHub:

- `DIGITALOCEAN_ACCESS_TOKEN`
- `FLASK_SECRET_KEY`
- `FIREBASE_ADMIN_CREDENTIALS_JSON`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `RESEND_API_KEY`
- `GOOGLE_OAUTH_CLIENT_SECRET=`

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

Add `vmswedenison.site` as the primary domain in App Platform.

Then apply the DNS records that DigitalOcean gives you for the apex domain. Wait for:

- DNS propagation
- TLS certificate issuance

After the app is live, verify:

- `https://vmswedenison.site/healthz`
- `https://vmswedenison.site/`
- `https://vmswedenison.site/privacy`
- `https://vmswedenison.site/dashboard`

For Google OAuth verification, use a custom domain you control. Do not submit the default `ondigitalocean.app` URL as the OAuth homepage because Google requires ownership of the homepage domain.

## 6. Configure Firebase for Production

In Firebase:

1. Add `vmswedenison.site` to Authorized domains.
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
2. Verify your production domain in Google Search Console.
3. Add the verified top private domain under OAuth authorized domains.
4. Set the OAuth homepage URL to `https://vmswedenison.site/`.
5. Set the privacy policy URL to `https://vmswedenison.site/privacy`.
6. Add the OAuth redirect URI `https://vmswedenison.site/google-calendar/oauth/callback`.

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

1. Open `https://vmswedenison.site/`.
2. Confirm the public homepage loads without login and links to `/privacy`.
3. Open `https://vmswedenison.site/privacy` and confirm the privacy policy loads without login.
4. Open `https://vmswedenison.site/dashboard` and confirm the dashboard auth shell loads.
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
