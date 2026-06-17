# Deployment

Foodie is a Streamlit app, so it needs a running Python server — it cannot be
hosted on static-only platforms like GitHub Pages. It is deployed on
[Streamlit Community Cloud](https://share.streamlit.io), which runs the app
unchanged and redeploys automatically on every push to the tracked branch.

## Continuous integration

Every pull request and every push to `main` runs
[`.github/workflows/ci.yml`](.github/workflows/ci.yml), which:

1. Checks formatting with `black --check` (Black default settings).
2. Runs the test suite with `pytest`.

Keep CI green before merging — Streamlit Community Cloud deploys from `main`
directly, so a red `main` ships a broken app.

## Deploying to Streamlit Community Cloud (one-time setup)

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with the GitHub
   account that can access this repository.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository**: this repo
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. (Optional) Under **Advanced settings**, set the **Python version** to match
   CI (`3.11`).
5. Configure secrets (see below), then click **Deploy**.

Dependencies install automatically from [`requirements.txt`](requirements.txt).

After the first deploy, every push to `main` triggers an automatic redeploy.

## Authentication secrets

The login gate in [`app.py`](app.py) is enabled only when `AUTH_USERNAME` is
present in the environment (see [`_build_authenticator`](app.py)). On Streamlit
Community Cloud, **top-level keys** in the app's secrets are exposed as
environment variables, so the existing `os.environ.get(...)` lookups work
without code changes.

In **Advanced settings → Secrets**, paste the values as top-level keys (TOML),
**not** under a `[section]` header:

```toml
AUTH_USERNAME = "admin"
AUTH_NAME = "Admin"
AUTH_PASSWORD_HASH = "$2b$12$...your-bcrypt-hash..."
AUTH_COOKIE_KEY = "a-long-random-secret"
AUTH_COOKIE_NAME = "foodie_auth"
```

Generate the bcrypt password hash with:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

See [`.env.example`](.env.example) for the same variables used in local
development. If you omit these secrets, the app deploys and runs **without** a
login gate — only acceptable for non-sensitive, public data.

## Known limitation: storage is ephemeral

Receipts are stored as CSV files under `data/` via
[`integrations/storage.py`](integrations/storage.py), which creates the
directory and files on first upload. The `data/` directory is **git-ignored**
(see [`.gitignore`](.gitignore)), so it is **not** part of the repository.
This means:

- The hosted app starts with **no receipts** — there is no seed/demo data.
- Streamlit Community Cloud's filesystem is **ephemeral** — it resets on reboot,
  redeploy, or when the app sleeps, so receipts uploaded on the hosted app will
  **not** persist long-term.

For durable storage, the app would need an external backing store (e.g. a
managed database or object storage) wired into `integrations/`. That is out of
scope for the current deployment.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
