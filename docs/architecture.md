# Architecture

`ucb_affiliations` is one package with three parts: a shared core at its top
level, and two subpackages - `cli` and `web` - that each present that core
differently. Nothing outside `ucb_affiliations` itself needs to import `cli`
or `web`; a downstream app like the account application only ever imports the
shared core (e.g. `from ucb_affiliations.affiliations import
determine_affiliations`).

```
ucb_affiliations/             # Shared core - the only part downstream apps import
├── affiliations.py           # Core affiliation-determination logic
├── flow_runner.py            # Runs the flowtoy flow, exposes on_status
│                             # callbacks for live per-source progress
├── spinner.py                # Live status display abstraction - used by the
│                             # CLI's terminal spinner, and (disabled) by
│                             # flow_runner.py itself, so it lives here rather
│                             # than under cli/
├── static_provider.py        # Custom flowtoy provider: static data injection
├── json_parser_provider.py   # Custom flowtoy provider: parses JSON strings
├── staff_courses_provider.py # Custom flowtoy provider: SIS teaching assignments
│
├── cli/                      # CLI-only presentation
│   ├── __main__.py           # Argument parsing, entry point
│   └── formatters.py         # human/json/bulk terminal output
│
└── web/                      # Web-only presentation
    ├── app.py                # Flask application factory + OIDC config
    ├── routes.py              # Route handlers (imports the shared core)
    ├── wsgi.py                # WSGI entry point for production
    ├── run.py                 # Development server runner
    └── templates/             # Jinja2 templates

# Shared configuration (both CLI and web)
flow-uid.yaml                   # Flow for CalNet UID input
flow-shortname.yaml             # Flow for shortname input
config.yaml.example             # Department configuration template
.env.example                    # Credential/config template (see each page
                                 # for which variables which tool needs)
```

## Dependencies

Every external tool the flow shells out to is an ordinary pip dependency
(see `pyproject.toml`): `ucbhr`, `sis`, `grouper`, `ldapsearch-json`, and
`calnet-resolve`. `pip install -e .` is all that's needed to get a working
CLI - there's no separate runtime dependency check to run.

## How providers find the department config

`staff_courses_provider.py` is instantiated generically by flowtoy from the
flow YAML (`type: staff_courses`), which has no channel to tell it which
`--config`/`config_file` the CLI or web app was actually given - so it falls
back to reading the department config itself, to get `courses.subject_areas`
when the flow step doesn't specify them directly. Both `cli/__main__.py` and
`web/app.py` set an env var, `UCB_AFFILIATIONS_CONFIG`, to whichever config
path they were actually told to use, and the provider reads that (falling
back to `config.yaml` if unset). Any future flowtoy provider that needs the
department config should use the same mechanism rather than hardcoding a
filename.

## Why share code

- Single source of truth for affiliation logic (`affiliations.py`)
- Same flows, same config, for both CLI and web
- Fix a bug once, both tools benefit
- CLI and web always agree on the result for a given user
