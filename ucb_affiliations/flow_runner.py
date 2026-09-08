"""Flowtoy flow runner for user lookups."""
import io
import logging
import os
import sys
from typing import Dict, Any, Tuple
from flowtoy.config import load_yaml_files
from flowtoy.runner import LocalRunner
from flowtoy.providers import _entry_point_providers

from .static_provider import StaticDataProvider
from .json_parser_provider import JsonParserProvider
from .staff_courses_provider import StaffCoursesProvider
from .spinner import StatusDisplay


# Label for the identity-lookup step injected at the start of the flow.
_IDENTITY_LABEL = "Identity"


def run_user_lookup(user_identifier: str, flow_file: str, is_uid: bool = True, show_status: bool = True, on_status: Any = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Run flowtoy flow to gather user information from multiple systems.

    Args:
        user_identifier: The user's CalNet UID (if is_uid=True) or CalNet shortname (if is_uid=False)
        flow_file: Path to the flow YAML file (or base name, will append -uid or -shortname)
        is_uid: Whether user_identifier is a CalNet UID (True) or shortname (False)
        show_status: Whether to show status indicators
        on_status: Optional callback(step_name, state, flows_snapshot, error)
            invoked on every step state transition (state is one of
            "running", "succeeded", "failed", "skipped"), in addition to the
            terminal status display. flows_snapshot is a shallow copy of the
            flow results gathered so far - when state is "succeeded" it
            always includes that step's own output, so callers can evaluate
            that step's result immediately rather than waiting for the whole
            flow to finish. error is the failure/skip reason (None on
            success). Lets non-terminal callers (e.g. the web app) observe
            the same live per-step progress the CLI spinner shows.

    Returns:
        Tuple of (flow_results, flow_errors)
        - flow_results: Dictionary containing successful flow step results
        - flow_errors: Dictionary mapping failed step names to error messages
        
    Raises:
        FileNotFoundError: If flow file doesn't exist
    """
    # Register custom providers with flowtoy
    _entry_point_providers['static'] = StaticDataProvider
    _entry_point_providers['json_parser'] = JsonParserProvider
    _entry_point_providers['staff_courses'] = StaffCoursesProvider
    
    # Capture the original stderr up-front. The flow suppresses flowtoy's
    # tracebacks by redirecting sys.stderr, so the live status display must
    # write to the captured original stream instead of the redirected one.
    original_stderr = sys.stderr
    display = StatusDisplay(enabled=show_status, stream=original_stderr)
    display.start()

    try:
        # Determine which flow file to use based on input type
        if is_uid:
            actual_flow_file = flow_file.replace('.yaml', '-uid.yaml')
        else:
            actual_flow_file = flow_file.replace('.yaml', '-shortname.yaml')
        
        if not os.path.exists(actual_flow_file):
            raise FileNotFoundError(f"Flow configuration file not found: {actual_flow_file}")
        
        display.set_phase("Loading flow configuration")
        # Load the flow configuration
        config = load_yaml_files([actual_flow_file])
        
        # Inject the user identifier into the flow config as static data
        if is_uid:
            # If UID provided, inject it directly
            config['sources']['uid_source'] = {
                'type': 'static',
                'configuration': {
                    'data': {
                        'calnet_uid': user_identifier
                    }
                }
            }
            uid_step = {
                'name': 'uid_lookup',
                'label': _IDENTITY_LABEL,
                'source': 'uid_source',
                'output': [
                    {'name': 'calnet_uid', 'type': 'jmespath', 'value': 'calnet_uid'}
                ]
            }
        else:
            # If shortname provided, we'll extract CalNet UID from dept LDAP
            config['sources']['shortname_source'] = {
                'type': 'static',
                'configuration': {
                    'data': {
                        'calnet_shortname': user_identifier
                    }
                }
            }
            uid_step = {
                'name': 'shortname_lookup',
                'label': _IDENTITY_LABEL,
                'source': 'shortname_source',
                'output': [
                    {'name': 'calnet_shortname', 'type': 'jmespath', 'value': 'calnet_shortname'}
                ]
            }
        
        # Insert at the beginning of the flow
        config['flow'].insert(0, uid_step)

        display.set_phase("")
        
        # Build step_name -> display label from the flow config (falls back to
        # the step name when no label is provided).
        step_labels: Dict[str, str] = {
            step.get('name'): step.get('label', step.get('name'))
            for step in config['flow']
            if step.get('name')
        }
        
        # Track which steps were configured
        all_steps = {step['name'] for step in config['flow']}
        
        # Seed rows as pending so the region is drawn before anything runs.
        # Use the same display labels that handle_status will emit, so rows
        # are keyed consistently.
        display.set_states(
            {step_labels.get(name, name): "pending" for name in all_steps}
        )
        
        # Run the flow - suppress stderr to avoid showing flowtoy error tracebacks
        # since we handle errors gracefully by reporting UNKNOWN status
        #
        # runner_ref defers access to the LocalRunner instance until after
        # it's constructed below (handle_status is passed to its
        # constructor, so it can't close over `runner` directly - by the
        # time any step actually completes and fires this callback,
        # runner_ref['runner'] has already been set).
        runner_ref: Dict[str, Any] = {}

        def handle_status(step_name: str, state: str):
            display.set_state(step_labels.get(step_name, step_name), state)
            if on_status is not None:
                try:
                    runner = runner_ref.get('runner')
                    flows_snapshot = dict(runner.flows) if runner is not None else {}
                    error = None
                    if runner is not None:
                        step_status = runner.status.steps.get(step_name)
                        error = step_status.error if step_status else None
                    if error is None:
                        if state == 'skipped':
                            error = 'skipped due to an earlier failure'
                        elif state == 'failed':
                            error = 'lookup failed'
                    on_status(step_name, state, flows_snapshot, error)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "on_status callback failed for step %s", step_name
                    )

        sys.stderr = io.StringIO()
        try:
            runner = LocalRunner(config, on_status=handle_status)
            runner_ref['runner'] = runner
            runner.run()
        finally:
            sys.stderr = original_stderr
        
        # Determine which steps failed (configured but not in results)
        successful_steps = set(runner.flows.keys())
        failed_steps = all_steps - successful_steps
        
        # Post-process: Copy CalNet UID to a standard location for output
        # For UID flow: already in uid_lookup.calnet_uid
        # For shortname flow: copy from calnet_lookup to uid_lookup
        if not is_uid and 'calnet_lookup' in runner.flows:
            calnet_uid = runner.flows['calnet_lookup'].get('calnet_uid')
            if calnet_uid:
                # Create uid_lookup in results if it doesn't exist (shortname flow uses shortname_lookup)
                if 'uid_lookup' not in runner.flows:
                    runner.flows['uid_lookup'] = {}
                runner.flows['uid_lookup']['calnet_uid'] = str(calnet_uid)
        
        # Create error messages for failed steps
        flow_errors = {}
        for step_name in failed_steps:
            step_status = runner.status.steps.get(step_name)
            detail = step_status.error if step_status else None
            if not detail:
                if step_status and step_status.state == 'skipped':
                    detail = 'skipped due to an earlier failure'
                else:
                    detail = 'lookup failed'
            flow_errors[step_name] = detail
        
        return runner.flows, flow_errors
    finally:
        display.stop()
