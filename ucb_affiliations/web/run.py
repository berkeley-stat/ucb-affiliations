#!/usr/bin/env python
"""
Development server runner for the affiliation web application.

For production deployment, use a WSGI server like gunicorn:
    gunicorn "ucb_affiliations.web.wsgi:app"
"""

import os
from ucb_affiliations.web.app import create_app

if __name__ == '__main__':
    # Load environment variables from .env file if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    app = create_app()
    
    # Run development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('ENV', 'dev') == 'dev'
    
    app.run(host='0.0.0.0', port=port, debug=debug)
