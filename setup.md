# Local setup

Run the Tender Intelligence Platform locally with a FastAPI backend and Next.js frontend. The steps below use PowerShell from the project root and do not require Docker.

## Prerequisites

- Python 3.12 or newer.
- Node.js 22 (the repository's `.nvmrc` version) and npm.
- Internet access for the initial dependency installation.

Check your tools:

```powershell
python --version
node --version
npm.cmd --version
```

## 1. Install dependencies

For a fresh checkout:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e "./backend[dev]"
Push-Location frontend
npm.cmd ci
Pop-Location
```

The `dev` extra includes `aiosqlite`, required for the local SQLite configuration. An existing, working environment can be reused. Do not copy a virtual environment from another machine; recreate it with your local Python installation.

## 2. Configure local services

Create environment files only if they do not already exist:

```powershell
if (!(Test-Path backend/.env)) {
    Copy-Item .env.backend.example backend/.env
}
if (!(Test-Path frontend/.env.local)) {
    Copy-Item .env.frontend.example frontend/.env.local
}
```

Set these values in `backend/.env`, preserving other settings:

```dotenv
ENVIRONMENT=local
DATABASE_URL=sqlite+aiosqlite:///./tender_intel.db
QDRANT_URL=
QDRANT_LOCAL_PATH=./.qdrant
EMBEDDING_BACKEND=hash
CORS_ALLOW_ORIGINS=http://localhost:3000
ALLOWED_EMAIL_DOMAINS=maheshwaricomputers.com
```

Generate a signing secret and paste the result into `JWT_SECRET` in `backend/.env`:

```powershell
backend/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `ALLOWED_EMAIL_DOMAINS` to your organization's domain, or add your exact email address to `ALLOWED_EMAIL_EXCEPTIONS`. Both accept comma-separated values. Registration requires an admitted address.

For a fresh database, optionally set `BOOTSTRAP_SUPER_ADMIN_EMAIL` to an admitted address **before running the first migration**. This provisions a role; you still need to register the account. Changing this value after the bootstrap migration has run does not rerun that migration.

In `frontend/.env.local`, set:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Email/password registration and login are supported. Google credentials are
optional. To enable Google, configure matching `GOOGLE_CLIENT_ID` and
`NEXT_PUBLIC_GOOGLE_CLIENT_ID` values; see [Google sign-in configuration](frontend/docs/google-sign-in.md).
Gemini credentials are optional for the AI analyst.

Keep real secrets in the environment files, not in documentation or source control.

## 3. Start the backend

Open a PowerShell terminal in the project root:

```powershell
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn tender_intel.api.app:app --host 127.0.0.1 --port 8000
```

Keep this terminal running. Launching from `backend` ensures the application loads the correct `.env` and local data paths. Run only one API process when using embedded Qdrant.

## 4. Start the frontend

Open another PowerShell terminal in the project root:

```powershell
cd frontend
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open [the application](http://localhost:3000). Visit [registration](http://localhost:3000/register) to create an account with an admitted email address and an 8–128 character password, or [log in](http://localhost:3000/login) with an existing account.

## 5. Verify and stop

```powershell
Invoke-RestMethod http://localhost:8000/health
(Invoke-WebRequest http://localhost:3000 -UseBasicParsing).StatusCode
```

Expected results: API status `ok`, version `0.1.0`, and frontend HTTP status `200`.

- Application: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/health>

Press `Ctrl+C` in each server terminal to stop it. To restart, repeat the backend and frontend startup commands; dependencies and environment files do not need to be recreated.

## Local data and limitations

The database is `backend/tender_intel.db`, vectors are in `backend/.qdrant/`, and documents are in `backend/.storage/`. Preserve these directories to retain local data.

Hash embeddings allow offline development but have lower semantic matching quality than FastEmbed. Deployment should use PostgreSQL and a Qdrant server. See [README.md](README.md) for Docker setup and deployment configuration.

## Troubleshooting

- **Port already in use:** Check whether the app is already running at the links above. Use `netstat -ano | Select-String ':3000|:8000'` to locate listeners and identify the process before stopping it. If you change ports, update the frontend API URL and backend CORS origin accordingly.
- **PowerShell blocks npm scripts:** Use `npm.cmd` as shown; virtual environment activation is unnecessary.
- **Python is unavailable:** Install Python 3.12+ and reopen your terminal. If the `python` command opens the Microsoft Store, use your installed Python executable or the `py` launcher.
- **Missing pip:** Run `backend/.venv/Scripts/python.exe -m ensurepip --upgrade`, then repeat the backend dependency installation.
- **Dependency metadata access errors:** Check whether your terminal or automation sandbox can read the virtual environment files. A metadata-related import failure can result from denied file access; verify permissions before reinstalling packages.
- **Missing database tables:** Run the Alembic command from `backend` and confirm `DATABASE_URL` points to the intended database.
- **API connection or CORS errors:** Confirm the backend health endpoint responds, the frontend API URL is `http://localhost:8000`, and you browse at `http://localhost:3000`. Restart the frontend after changing its environment file.
- **Registration rejected:** Confirm the address matches an allowed domain or exact email exception. An empty admission configuration rejects all addresses.
- **Qdrant connection refused:** For local embedded mode, explicitly leave `QDRANT_URL` empty and set `QDRANT_LOCAL_PATH=./.qdrant`.

On macOS/Linux, use `python3`, `backend/.venv/bin/python`, and `npm`, and adapt the file-copy commands to your shell.
