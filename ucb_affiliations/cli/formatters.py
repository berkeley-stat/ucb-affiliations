"""Output formatters for affiliation results."""
from typing import Dict, Any
import json


def _format_status(value):
    """Format a boolean/None status value."""
    if value is True:
        return 'YES'
    elif value is False:
        return 'NO'
    else:
        return 'UNKNOWN'


def format_output_human(calnet_uid: str, affiliations: Dict[str, Any]) -> str:
    """
    Format output for human-readable display.
    
    Args:
        calnet_uid: The user's CalNet UID
        affiliations: Affiliation results
        
    Returns:
        Formatted string
    """
    lines = []
    lines.append(f"\nUser: {calnet_uid}")
    lines.append("")
    
    # Summary
    lines.append("Summary:")
    lines.append(f"  Employee:                    {_format_status(affiliations['employee'])}")
    lines.append(f"  Student:                     {_format_status(affiliations['student'])}")
    lines.append(f"  Enrolled in Department Courses: {_format_status(affiliations['enrolled_in_courses'])}")
    lines.append(f"  Group Member:                {_format_status(affiliations['group_member'])}")
    lines.append(f"  LDAP User:                   {_format_status(affiliations.get('ldap_user'))}")
    lines.append(f"  Teaching Staff:              {_format_status(affiliations.get('teaching_staff'))}")
    
    # Show errors if any
    if affiliations.get('errors'):
        lines.append("\nLookup Errors:")
        for step_name, error_msg in affiliations['errors'].items():
            # Make the step name more human-readable
            display_name = step_name.replace('_lookup', '').replace('_', ' ').title()
            lines.append(f"  - {display_name}: {error_msg}")
    
    # Details
    if affiliations['details']['jobs']:
        lines.append("\nEmployment Details:")
        for job in affiliations['details']['jobs']:
            marker = "" if job.get('dept_match', True) else " [non-dept]"
            lines.append(f"  - {job['title']} ({job['department']}){marker}")
    
    if affiliations['details']['programs']:
        lines.append("\nAcademic Programs:")
        for program in affiliations['details']['programs']:
            marker = "" if program.get('dept_match', True) else " [non-dept]"
            lines.append(f"  - {program['program']} - {program['status']}{marker}")
    
    if affiliations['details']['courses']:
        lines.append("\nCurrent Courses:")
        for course in affiliations['details']['courses']:
            marker = "" if course.get('dept_match', True) else " [non-dept]"
            lines.append(f"  - {course['course']}: {course['title']}{marker}")

    if affiliations['details'].get('staff_assignments'):
        lines.append("\nInstruction Assignments:")
        for assignment in affiliations['details']['staff_assignments']:
            marker = "" if assignment.get('dept_match', True) else " [non-dept]"
            component = f" ({assignment['component']})" if assignment.get('component') else ""
            lines.append(f"  - {assignment['course']}{component}: {assignment['role']}{marker}")
    
    if affiliations['details']['groups']:
        lines.append("\nGroup Memberships:")
        for group in affiliations['details']['groups']:
            marker = "" if group.get('dept_match', True) else " [non-dept]"
            lines.append(f"  - {group['name']}{marker}")
    
    lines.append("")
    return "\n".join(lines)


def format_output_bulk(calnet_uid: str, affiliations: Dict[str, Any]) -> str:
    """
    Format output for bulk reporting (tab-separated).
    
    Args:
        calnet_uid: The user's CalNet UID
        affiliations: Affiliation results
        
    Returns:
        Tab-separated values
    """
    def _to_bulk(value):
        """Convert boolean/None to bulk format."""
        if value is True:
            return "1"
        elif value is False:
            return "0"
        else:
            return "?"
    
    return "\t".join([
        calnet_uid,
        _to_bulk(affiliations['employee']),
        _to_bulk(affiliations['student']),
        _to_bulk(affiliations['enrolled_in_courses']),
        _to_bulk(affiliations['group_member']),
        _to_bulk(affiliations.get('ldap_user')),
        _to_bulk(affiliations.get('teaching_staff'))
    ])


def format_output_json(calnet_uid: str, affiliations: Dict[str, Any]) -> str:
    """
    Format output as JSON.
    
    Args:
        calnet_uid: The user's CalNet UID
        affiliations: Affiliation results
        
    Returns:
        JSON string
    """
    output = {
        'calnet_uid': calnet_uid,
        'affiliations': affiliations
    }
    return json.dumps(output, indent=2)
