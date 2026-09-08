"""
WSGI entry point for production deployment.

Usage with gunicorn:
    gunicorn "ucb_affiliations.web.wsgi:app"

Usage with other WSGI servers:
    from ucb_affiliations.web.wsgi import app
"""

from ucb_affiliations.web.app import create_app

app = create_app()
