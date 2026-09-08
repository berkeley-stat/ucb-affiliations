"""Main entry point for the affiliation lookup CLI tool."""
import argparse
import os
import sys
import yaml

from ..flow_runner import run_user_lookup
from ..affiliations import determine_affiliations
from .formatters import format_output_human, format_output_bulk, format_output_json
from ..spinner import StatusDisplay


def main():
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description='Look up user affiliations across multiple systems',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Look up a user with status indicators
  %(prog)s 12345

  # Look up a user without status indicators (for scripting)
  %(prog)s 12345 --no-status

  # Output in JSON format
  %(prog)s 12345 --format json

  # Bulk reporting mode (tab-separated, no status)
  %(prog)s 12345 --format bulk --no-status
  
  # Show all affiliations (not just department-specific)
  %(prog)s 12345 --show-all
  
  # Lookup by CalNet shortname instead of UID
  %(prog)s username --show-all
        """
    )
    
    parser.add_argument(
        'user_identifier',
        help='CalNet UID (numeric) or CalNet shortname to look up'
    )
    
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to department configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--flow',
        default='flow.yaml',
        help="Base name of the flow configuration file - '-uid' or '-shortname' "
             "is inserted before .yaml depending on the identifier given "
             "(default: flow.yaml -> flow-uid.yaml/flow-shortname.yaml)"
    )
    
    parser.add_argument(
        '--no-status',
        action='store_true',
        help='Disable status indicators (useful for bulk reporting)'
    )
    
    parser.add_argument(
        '--format',
        choices=['human', 'json', 'bulk'],
        default='human',
        help='Output format: human (default), json, or bulk (tab-separated)'
    )
    
    parser.add_argument(
        '--show-all',
        action='store_true',
        help='Show all affiliations (not just department-specific ones)'
    )
    
    args = parser.parse_args()
    
    # Auto-detect if input is UID (numeric) or shortname (non-numeric)
    is_uid = args.user_identifier.isdigit()
    
    # Determine if we should show status
    show_status = not args.no_status and args.format != 'bulk'

    # Let flowtoy providers instantiated generically from the flow YAML
    # (e.g. StaffCoursesProvider) find the same config file we were told to
    # use, since there's no other channel to pass it to them.
    os.environ['UCB_AFFILIATIONS_CONFIG'] = args.config

    # Load department configuration
    try:
        if not os.path.exists(args.config):
            print(f"Error: Configuration file '{args.config}' not found", file=sys.stderr)
            print(f"Please create a department configuration file at {args.config}", file=sys.stderr)
            sys.exit(1)
            
        with open(args.config, 'r') as f:
            dept_config = yaml.safe_load(f)
            
        if not dept_config:
            print("Error: Invalid configuration file format", file=sys.stderr)
            print(f"Configuration file {args.config} is empty or invalid", file=sys.stderr)
            sys.exit(1)
            
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse configuration file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check flow file exists. run_user_lookup() actually loads a transformed
    # name (-uid/-shortname appended, see flow_runner.py), not args.flow
    # itself, so check for the file it will really try to open.
    actual_flow_file = args.flow.replace('.yaml', '-uid.yaml' if is_uid else '-shortname.yaml')
    if not os.path.exists(actual_flow_file):
        print(f"Error: Flow configuration file '{actual_flow_file}' not found", file=sys.stderr)
        print(f"Please create a flow configuration file at {actual_flow_file}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Run the user lookup
        flow_results, flow_errors = run_user_lookup(
            args.user_identifier, 
            args.flow, 
            is_uid=is_uid,
            show_status=show_status
        )
        
        # Determine affiliations
        with StatusDisplay(enabled=show_status) as analyze_display:
            analyze_display.set_phase("Analyzing affiliations")
            affiliations = determine_affiliations(flow_results, dept_config, flow_errors, show_all=args.show_all)
        
        # Output results (use the actual CalNet UID for display, not the input identifier)
        calnet_uid = flow_results.get('uid_lookup', {}).get('calnet_uid', args.user_identifier)
        if args.format == 'json':
            print(format_output_json(calnet_uid, affiliations))
        elif args.format == 'bulk':
            print(format_output_bulk(calnet_uid, affiliations))
        else:  # human
            print(format_output_human(calnet_uid, affiliations))
        
        # Exit with code 0 if user has any affiliation
        # Exit with code 1 if no affiliation (but all checks succeeded)
        # Exit with code 2 if any checks failed (already handled in except block)
        has_affiliation = any([
            affiliations['employee'] is True,
            affiliations['student'] is True,
            affiliations['enrolled_in_courses'] is True,
            affiliations['group_member'] is True,
            affiliations.get('ldap_user') is True
        ])
        sys.exit(0 if has_affiliation else 1)
        
    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        import traceback
        if show_status:
            print(f"\nError: {e}", file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        if os.getenv('DEBUG'):
            traceback.print_exc()
        sys.exit(2)


if __name__ == '__main__':
    main()
