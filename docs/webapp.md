# Web Application

A Flask web application for checking user affiliations with a department via OIDC authentication.

## Features

- **OIDC Authentication**: Integrates with any OIDC provider (CalNet, Okta, Azure AD, etc.)
- **Multi-System Lookups**: Queries HR, SIS, LDAP, and Grouper systems in parallel using flowtoy
- **Department-Specific Configuration**: Configurable criteria for determining affiliations
- **Shared Core Logic**: Reuses the same affiliation detection code as the CLI tool

See [Architecture](architecture.md) for how this shares code with the CLI tool.

## Installation

### Install the package with web app dependencies:

```bash
pip install -e ".[webapp]"
```

### Or install all dependencies manually:

```bash
pip install Flask Authlib requests cryptography python-dotenv gunicorn
pip install git+https://github.com/berkeley-stat/flask-oidc.git
```

## Configuration

### 1. Environment Variables

**For development**, copy `.env.example` (in the repo root) to `.env` and fill it in -
it covers both the Flask/OIDC settings below and the external-system credentials
(`GROUPER_*`, `UCBHR_*`, `SIS_*`, `CALNET_RESOLVE_*`) the underlying flow needs
regardless of CLI vs web.

```bash
# Flask configuration
ENV=dev                          # dev, test, or prod
SECRET_KEY=your-secret-key-here  # Change in production!
PORT=5000

# OIDC configuration
CLIENT_ID=your-oidc-client-id
CLIENT_SECRET=your-oidc-client-secret
CALNET_ENVIRONMENT=prod          # For CalNet: 'test' or 'prod'
```

If `CLIENT_ID`/`CLIENT_SECRET` aren't set, the app runs unauthenticated
(local dev mode) - see the admin `/lookup` tool below.

**For production**, environment variables should be provided by your deployment platform:
- Docker/Kubernetes: Use secrets and ConfigMaps
- systemd: Use `Environment=` directives in service files
- Cloud platforms (AWS/GCP/Azure): Use their secret management services
- Apache/nginx: Set via `SetEnv` directives
- Docker Compose: Use `environment:` or `env_file:` in `docker-compose.yml`

The `.env` file is only loaded in development for convenience (via `python-dotenv`).

### 2. Department Configuration

Copy `config.yaml.example` to `config.yaml` and edit it to match your department:

```yaml
name: "Statistics Department"

employment:
  hr_dept_numbers:
    - "PSTAT"

student:
  academic_plan_codes:
    - "00891PHDG"  # Statistics PhD

courses:
  subject_areas:
    - "STAT"

groups:
  folder_prefixes:
    - "edu:berkeley:org:stat:stat-computing:scf-users-research-groups"

admins:
  users:
    - "12345"   # CalNet UIDs/shortnames allowed to use /lookup
```

## Running the Application

### Development Server

```bash
# Run the development server (reads from .env.dev or .env)
python -m ucb_affiliations.web.run

# Or directly:
python ucb_affiliations/web/run.py
```

The app will be available at `http://localhost:5000`

### Production Deployment

Use a WSGI server like gunicorn. Environment variables should be set by your deployment platform, not from `.env` files.

```bash
# Basic usage (env vars set by deployment platform)
gunicorn "ucb_affiliations.web.wsgi:app"

# With options
gunicorn "ucb_affiliations.web.wsgi:app" \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
```

**Example: systemd service file**
```ini
[Unit]
Description=Affiliation Web App
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/ucb-affiliations
Environment="ENV=prod"
Environment="SECRET_KEY=<your-secret-key>"
Environment="CLIENT_ID=<your-client-id>"
Environment="CLIENT_SECRET=<your-client-secret>"
Environment="GROUPER_USER=<username>"
Environment="GROUPER_PASS=<password>"
ExecStart=/opt/ucb-affiliations/venv/bin/gunicorn "ucb_affiliations.web.wsgi:app" --bind 0.0.0.0:8000

[Install]
WantedBy=multi-user.target
```

**Example: Docker Compose**
```yaml
services:
  webapp:
    build: .
    ports:
      - "8000:8000"
    environment:
      ENV: prod
      SECRET_KEY: ${SECRET_KEY}
      CLIENT_ID: ${CLIENT_ID}
      CLIENT_SECRET: ${CLIENT_SECRET}
      GROUPER_USER: ${GROUPER_USER}
      GROUPER_PASS: ${GROUPER_PASS}
    # Or use secrets for sensitive data
    secrets:
      - client_secret
      - grouper_pass
```

### Docker Deployment

No `Dockerfile`/`docker-compose.yml` ship with this repo yet - the gunicorn
command above and the Compose snippet earlier are what one would build
around.

## OIDC Provider Configuration

### CalNet (UC Berkeley)

The app is pre-configured for CalNet. Register your application at:
- Test: https://auth-test.berkeley.edu
- Prod: https://auth.berkeley.edu

Required scopes:
- `openid`, `profile`, `email` (standard)
- `berkeley_edu_default`, `berkeley_edu_groups`, `berkeley_edu_dept_number`, `berkeley_edu_ou` (CalNet-specific, require approval)

### Other OIDC Providers

The app uses the generic `flask-oidc` library and can work with any OIDC provider. Just set the environment variables accordingly.

## Routes

- `/` - Home page (redirects to login or affiliations)
- `/affiliations` - Display the logged-in user's own affiliations (requires auth)
- `/lookup` - Admin tool: look up affiliations for another CalNet UID/shortname, with
  live per-source results (requires auth + membership in `config.yaml`'s `admins.users`,
  or no auth at all in local dev mode)
- `/lookup/stream` - Server-Sent Events endpoint backing `/lookup`'s live updates
- `/user-info` - Display raw OIDC user claims (requires auth)
- `/login` - Initiate OIDC login (auto-registered by flask-oidc)
- `/oauth_callback` - OIDC callback handler (auto-registered by flask-oidc)
- `/logout` - Logout from application and OIDC provider (auto-registered by flask-oidc)
- `/auth-error` - Authentication error page

## How It Works

1. **User Authentication**: User clicks "Login" → redirected to OIDC provider → returns with ID token
2. **Extract CalNet UID**: From OIDC claims (`sub` or `uid` field)
3. **Auto-Detect Input Type**: Numeric = UID, non-numeric = shortname
4. **Select Flow**: Choose `flow-uid.yaml` or `flow-shortname.yaml`
5. **Run Flowtoy Workflow**: Query HR, SIS, LDAP, Grouper in parallel
6. **Determine Affiliations**: Use shared `determine_affiliations()` logic
7. **Display Results**: Render affiliation status + details, live per-source on `/lookup`

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[webapp,dev]"

# Run tests
pytest

# Run development server with auto-reload
ENV=dev python ucb_affiliations/web/run.py
```

## Security Considerations

- Change `SECRET_KEY` in production
- Use HTTPS in production (behind nginx/Apache)
- Set `ENV=prod` to disable debug mode
- Keep OIDC client credentials secure
- Use ProxyFix middleware when behind a reverse proxy (already configured)
- Replace the `"CHANGEME"` placeholder in `config.yaml`'s `admins.users` before relying on `/lookup`'s access control

## Troubleshooting

### "CLIENT_ID and CLIENT_SECRET must be set"
- Set these environment variables in your `.env` file or shell, or omit both to run in local dev mode without auth

### "ImportError: No module named flask_oidc"
- Install the flask-oidc library: `pip install git+https://github.com/berkeley-stat/flask-oidc.git`

### LDAP lookups fail
- Make sure you're on the campus network or VPN
- Check LDAP credentials if using authenticated LDAP

### Grouper lookups show UNKNOWN
- Set `GROUPER_USER` and `GROUPER_PASS` in your `.env` file
- Check that the credentials are correct
