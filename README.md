# UCB Affiliation

Tools for looking up a UC Berkeley user's affiliation with a department -
employment, academic programs, course enrollment, group membership, and
teaching/TA assignments - across HR, SIS, Grouper, and LDAP. Ships as a CLI
(`affiliation-lookup`) and a Flask web app, sharing the same core lookup logic.

## Install

```bash
pip install -e .            # CLI only
pip install -e ".[webapp]"  # CLI + web app
```

## Documentation

See [`docs/`](docs/) for full documentation - CLI usage, web app setup and
deployment, and architecture. Build it locally with:

```bash
cd docs
myst start
```
