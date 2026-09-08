"""
Route handlers for the affiliation web application.
"""

import json
import queue
import threading

from flask import current_app, redirect, render_template, request, Response, stream_with_context, url_for
from ..flow_runner import run_user_lookup
from ..affiliations import determine_affiliations, determine_single_affiliation, STEP_EVALUATORS

# Which affiliations.py detail-list a given step's result belongs under, for
# rendering that step's own detail items inline in its /lookup status row.
# dept_ldap_lookup has no detail list (just a yes/no).
STEP_DETAIL_KIND = {
    'jobs_lookup': 'jobs',
    'sis_plans': 'programs',
    'sis_courses': 'courses',
    'grouper_lookup': 'groups',
    'staff_assignments_lookup': 'staff_assignments',
}

# Which affiliations.py status field a given step's result belongs under -
# the inverse of STEP_DETAIL_KIND, used to build a final catch-up summary
# (see _stream_lookup_events) from the already-computed aggregate result,
# for any row that never got its own live "result" event.
STEP_STATUS_KEY = {
    'jobs_lookup': 'employee',
    'sis_plans': 'student',
    'sis_courses': 'enrolled_in_courses',
    'grouper_lookup': 'group_member',
    'dept_ldap_lookup': 'ldap_user',
    'staff_assignments_lookup': 'teaching_staff',
}


def _run_lookup(user_identifier, on_status=None):
    """Run the affiliation flow for a given CalNet UID or shortname.

    Returns (dept_name, affiliations, error). On failure, dept_name and
    affiliations are None and error holds a message. If given, on_status
    (step_name, state, flows_snapshot, error) is forwarded to
    run_user_lookup and fires as each source's lookup starts/finishes (see
    flow_runner.run_user_lookup).
    """
    dept_config = current_app.config['DEPT_CONFIG']
    dept_name = dept_config.get('department', {}).get('name', 'Statistics Department')
    is_uid = str(user_identifier).isdigit()

    try:
        flow_results, flow_errors = run_user_lookup(
            str(user_identifier),
            flow_file='flow.yaml',
            is_uid=is_uid,
            show_status=False,
            on_status=on_status
        )
        affiliations = determine_affiliations(
            flow_results,
            dept_config,
            flow_errors=flow_errors,
            show_all=False
        )
        return dept_name, affiliations, None
    except Exception as e:
        current_app.logger.error(f"Error running affiliation check for {user_identifier}: {e}")
        return dept_name, None, str(e)


def _is_admin_user(user):
    """Check whether an authenticated OIDC user is allowed to use /lookup.

    Currently checks a static list in config.yaml (admins.users). Swap this
    out for a Grouper group membership check later without touching the
    /lookup route itself.
    """
    dept_config = current_app.config['DEPT_CONFIG']
    admin_users = {str(u) for u in dept_config.get('admins', {}).get('users', [])}

    candidates = {
        str(user.get('sub') or ''),
        str(user.get('uid') or ''),
        str(user.get('preferred_username') or ''),
    }
    candidates.discard('')

    return bool(candidates & admin_users)


def _lookup_access_denied():
    """Check whether the current request may use /lookup or /lookup/stream.

    Returns None if access is allowed, or a Flask response to return
    immediately otherwise (redirect to login, or a 403).
    """
    oidc = current_app.config['OIDC']
    if oidc is None:
        return None  # dev mode: no auth configured at all

    if not oidc.is_authenticated():
        return redirect(url_for('oidc_login'))

    if not _is_admin_user(oidc.get_user()):
        return render_template(
            'error.html',
            error='You are not authorized to use the lookup tool.'
        ), 403

    return None


def _stream_lookup_events(app, user_identifier):
    """Generator yielding Server-Sent Events for a lookup's progress.

    Runs the flow in a background thread and forwards each on_status
    callback to the request-handling generator via a queue. As soon as an
    individual source's step finishes (succeeded/failed/skipped), its
    affiliation category is evaluated immediately from that step's own data
    (see ucb_affiliations.affiliations.determine_single_affiliation) and
    pushed as a "result" event - the client doesn't wait for the whole flow
    to fill in one source's box. A final "done" (or "lookup_error") event
    signals the stream is finished.

    Every event is a plain SSE "data:" message carrying a JSON object with a
    "type" field the client switches on, rather than distinct named SSE
    event types.
    """
    events = queue.Queue()

    def on_status(step_name, state, flows_snapshot, error):
        if state == 'running':
            events.put({'type': 'status', 'step': step_name, 'state': state})
            return

        if step_name not in STEP_EVALUATORS:
            return  # identity-resolution step, not shown as its own row

        # Evaluate just this step's category now, from just this step's own
        # data - no need to wait for the other sources to finish.
        flow_errors_for_step = {step_name: error} if state in ('failed', 'skipped') else {}
        with app.app_context():
            dept_config = app.config['DEPT_CONFIG']
            evaluated = determine_single_affiliation(
                step_name, flows_snapshot, dept_config, flow_errors_for_step, show_all=False
            )
            detail_html = ''
            if state == 'succeeded':
                kind = STEP_DETAIL_KIND.get(step_name)
                if kind and evaluated['details']:
                    detail_html = render_template('_category_detail.html', kind=kind, items=evaluated['details'])
            else:
                detail_html = render_template('_category_error.html', error=error or 'lookup failed')

        events.put({
            'type': 'result',
            'step': step_name,
            'state': state,
            'status': evaluated['status'],
            'detail_html': detail_html,
        })

    result = {}

    def worker():
        with app.app_context():
            dept_name, affiliations, error = _run_lookup(user_identifier, on_status=on_status)
            result['affiliations'] = affiliations
            result['error'] = error
        events.put(None)  # sentinel: worker is done

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        event = events.get()
        if event is None:
            break
        yield f"data: {json.dumps(event)}\n\n"

    thread.join()

    if result.get('error'):
        yield f"data: {json.dumps({'type': 'lookup_error', 'error': result['error']})}\n\n"
        return

    # Build a final catch-up summary from the same aggregate result
    # determine_affiliations() already computed. This covers two cases:
    # rows that finished normally (redundant with their earlier live
    # "result" event - the client only applies it if that row is still
    # empty) and rows that never got one at all, because an upstream step
    # (e.g. the shortname flow's identity-resolution step) failed and
    # flowtoy's default on_error:fail policy aborts the whole run without
    # ever marking dependent steps failed/skipped - they'd otherwise be
    # stuck showing a spinner forever.
    affiliations = result['affiliations']
    flow_errors = affiliations.get('errors') or {}

    # An error on a step that isn't one of the six rows (e.g. identity
    # resolution itself) is fatal to the whole lookup and wouldn't
    # otherwise be shown anywhere in the live view.
    identity_errors = {k: v for k, v in flow_errors.items() if k not in STEP_EVALUATORS}

    summary = {}
    with app.app_context():
        for step_name, status_key in STEP_STATUS_KEY.items():
            error_text = flow_errors.get(step_name)
            if error_text:
                detail_html = render_template('_category_error.html', error=error_text)
            else:
                kind = STEP_DETAIL_KIND.get(step_name)
                items = affiliations.get('details', {}).get(kind, []) if kind else []
                detail_html = render_template('_category_detail.html', kind=kind, items=items) if kind and items else ''
            summary[step_name] = {'status': affiliations.get(status_key), 'detail_html': detail_html}

    payload = {'type': 'done', 'summary': summary}
    if identity_errors:
        payload['identity_error'] = '; '.join(f'{k}: {v}' for k, v in identity_errors.items())
    yield f"data: {json.dumps(payload)}\n\n"


def init_app(app):
    """Register routes with the Flask application."""

    @app.route('/')
    def index():
        """Home page - shows login button if not authenticated, affiliations if authenticated"""
        oidc = current_app.config['OIDC']
        if oidc is None:
            return redirect(url_for('lookup'))
        if oidc.is_authenticated():
            return redirect(url_for('affiliations'))
        return render_template('home.html', env=current_app.config['ENV'])

    @app.route('/affiliations')
    def affiliations():
        """Display the logged-in user's own department affiliations"""
        oidc = current_app.config['OIDC']

        if oidc is None:
            return redirect(url_for('lookup'))

        if not oidc.is_authenticated():
            return redirect(url_for('oidc_login'))

        user = oidc.get_user()
        calnet_uid = user.get('sub') or user.get('uid')

        dept_name, user_affiliations, error = _run_lookup(calnet_uid)
        if error:
            return render_template('error.html', error=error)

        return render_template(
            'affiliations.html',
            dept_name=dept_name,
            user_id=calnet_uid,
            affiliations=user_affiliations
        )

    @app.route('/lookup', methods=['GET', 'POST'])
    def lookup():
        """Admin tool: look up affiliations for an arbitrary CalNet UID/shortname.

        Requires no auth when OIDC is not configured (local dev). When OIDC
        is configured, requires login and membership in the configured admin
        list (see _is_admin_user).
        """
        denied = _lookup_access_denied()
        if denied is not None:
            return denied
        dev_mode = current_app.config['OIDC'] is None

        dept_config = current_app.config['DEPT_CONFIG']
        dept_name = dept_config.get('department', {}).get('name', 'Statistics Department')
        user_id = None
        user_affiliations = None
        error = None

        if request.method == 'POST':
            user_id = request.form.get('user_identifier', '').strip()
            if user_id:
                dept_name, user_affiliations, error = _run_lookup(user_id)
            else:
                error = 'Enter a CalNet UID or shortname.'

        return render_template(
            'lookup.html',
            dept_name=dept_name,
            user_id=user_id,
            affiliations=user_affiliations,
            error=error,
            dev_mode=dev_mode
        )

    @app.route('/lookup/stream')
    def lookup_stream():
        """SSE endpoint: streams per-source status events for a lookup, then
        a final 'done' (or 'error') event with the rendered results.

        Same access rules as /lookup. Progressive enhancement for the
        lookup form's JS - the plain POST to /lookup still works standalone.
        """
        denied = _lookup_access_denied()
        if denied is not None:
            return denied

        user_id = request.args.get('user', '').strip()
        if not user_id:
            return Response(
                'data: {"type": "lookup_error", "error": "No user specified."}\n\n',
                mimetype='text/event-stream'
            )

        app_obj = current_app._get_current_object()
        return Response(
            stream_with_context(_stream_lookup_events(app_obj, user_id)),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',  # tell nginx not to buffer this response
            }
        )

    @app.route('/user-info')
    def user_info():
        """Display authenticated user information"""
        oidc = current_app.config['OIDC']

        if oidc is None:
            return redirect(url_for('lookup'))

        if not oidc.is_authenticated():
            return redirect(url_for('oidc_login'))

        user = oidc.get_user()
        return render_template('user_info.html', user=user)

    @app.route('/auth-error')
    def auth_error():
        """Display authentication error"""
        error = 'An authentication error occurred. Please try again.'
        return render_template('error.html', error=error)

    @app.route('/favicon.ico')
    def favicon():
        """Avoid routing favicon requests through the catch-all error handler."""
        return '', 204

    @app.errorhandler(Exception)
    def handle_auth_error(e):
        """Handle authentication errors"""
        # Don't handle HTTP exceptions (404, 500, etc.) - let Flask render its
        # normal response for those. Returning (not raising) the exception
        # lets Flask use it as the response directly; raising it here would
        # escalate it into an unhandled 500 instead.
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e

        current_app.logger.error(f"Error: {e}")
        return redirect(url_for('auth_error'))
