"""
Flask app factory and configuration for the affiliation web application.
"""

import os
import yaml
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_oidc import FlaskOIDC


def create_app(config_file='config.yaml'):
    """
    Create and configure the Flask application.
    
    Args:
        config_file: Path to department configuration file
        
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Basic Flask configuration
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Handle proxy headers (for X-Forwarded-Proto, etc.)
    # Must be applied early so all request processing sees the correct environ
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Load department configuration. config_file is resolved relative to the
    # project root (three levels up from this file: web/ -> ucb_affiliations/ -> root),
    # where the deployer's config.yaml lives (see config.yaml.example).
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_path = os.path.join(project_root, config_file)

    # Let flowtoy providers instantiated generically from the flow YAML
    # (e.g. StaffCoursesProvider) find the same config file - there's no
    # other channel to pass it to them. Use the fully-resolved path, not
    # config_file as given, since those providers open it relative to
    # whatever the process's cwd happens to be at request time (which may
    # not be project_root under e.g. gunicorn).
    os.environ['UCB_AFFILIATIONS_CONFIG'] = config_path

    with open(config_path, 'r') as f:
        dept_config = yaml.safe_load(f)
    app.config['DEPT_CONFIG'] = dept_config
    
    # Environment configuration
    app.config['ENV'] = os.environ.get('ENV', 'dev')
    
    # CalNet OIDC Configuration
    client_id = os.environ.get('CLIENT_ID')
    client_secret = os.environ.get('CLIENT_SECRET')
    calnet_environment = os.environ.get('CALNET_ENVIRONMENT', 'prod')

    # If no CalNet credentials are configured, skip OIDC entirely. This lets
    # the app run as a local, unauthenticated dev server (see /lookup) since
    # the registered CalNet clients are bound to specific scf.berkeley.edu
    # callback URLs and can't be exercised from localhost anyway.
    if not client_id or not client_secret:
        app.config['OIDC'] = None
    else:
        # CalNet OIDC server URLs
        calnet_servers = {
            'test': 'https://auth-test.berkeley.edu',
            'prod': 'https://auth.berkeley.edu'
        }

        # CalNet-specific scopes
        # See: https://calnet.berkeley.edu/calnet-technologists/single-sign/openid-connect/oidc-scopes-and-claims
        app_scopes = [
            'openid',
            'profile',
            'email',
            'berkeley_edu_default',
            'berkeley_edu_groups',
            'berkeley_edu_dept_number',
            'berkeley_edu_ou'
        ]

        # Get CalNet server URL for the environment
        oidc_server = calnet_servers.get(calnet_environment, calnet_servers['prod'])

        # Initialize OIDC authentication with CalNet configuration
        oidc = FlaskOIDC(
            app,
            client_id=client_id,
            client_secret=client_secret,
            oidc_server=oidc_server,
            server_metadata_path='/cas/oidc/.well-known/openid-configuration',
            logout_redirect_url=f'{oidc_server}/cas/oidc/oidcLogout',
            scopes=app_scopes
        )

        # Store OIDC instance in app config for route access
        app.config['OIDC'] = oidc
    
    # Register blueprints/routes
    from . import routes
    routes.init_app(app)
    
    return app
