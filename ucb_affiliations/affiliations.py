"""Affiliation determination logic."""
from typing import Any, Dict, Optional


def _dept_hr_numbers(dept_config: Dict[str, Any]) -> set:
    if 'employment' in dept_config:
        return set(dept_config['employment'].get('hr_dept_numbers', []))
    return set(dept_config.get('department', {}).get('hr_dept_numbers', []))


def _dept_plan_codes(dept_config: Dict[str, Any]) -> set:
    if 'student' in dept_config:
        return set(dept_config['student'].get('academic_plan_codes', []))
    return set(dept_config.get('department', {}).get('academic_plan_codes', []))


def _dept_subject_areas(dept_config: Dict[str, Any]) -> set:
    if 'courses' in dept_config:
        return set(dept_config['courses'].get('subject_areas', []))
    return set(dept_config.get('department', {}).get('course_subject_areas', []))


def _dept_folder_prefixes(dept_config: Dict[str, Any]) -> list:
    if 'groups' in dept_config:
        return dept_config['groups'].get('folder_prefixes', [])
    folder_prefix = dept_config.get('department', {}).get('grouper_folder', '')
    return [folder_prefix] if folder_prefix else []


def _evaluate_employee(flow_results, dept_config, flow_errors, show_all):
    status = None if 'jobs_lookup' in flow_errors else False
    details = []
    if 'jobs_lookup' in flow_errors or 'jobs_lookup' not in flow_results:
        return {'status': status, 'details': details}

    jobs_data = flow_results['jobs_lookup'].get('jobs') or []
    dept_numbers = _dept_hr_numbers(dept_config)

    for job in jobs_data:
        if not isinstance(job, dict):
            continue
        dept_code = job.get('department', {}).get('code')
        is_dept_job = dept_code in dept_numbers

        if is_dept_job:
            status = True

        if is_dept_job or show_all:
            job_code = job.get('jobCode', {})
            title = (job.get('description')
                     or job_code.get('code', {}).get('description')
                     or job_code.get('description'))
            details.append({
                'title': title,
                'department': job.get('department', {}).get('description'),
                'dept_match': is_dept_job
            })

    return {'status': status, 'details': details}


def _evaluate_student(flow_results, dept_config, flow_errors, show_all):
    status = None if 'sis_plans' in flow_errors else False
    details = []
    if 'sis_plans' in flow_errors or 'sis_plans' not in flow_results:
        return {'status': status, 'details': details}

    programs_list = flow_results['sis_plans'].get('programs') or []
    plan_codes = _dept_plan_codes(dept_config)

    if isinstance(programs_list, list):
        for program in programs_list:
            if not isinstance(program, dict):
                continue
            # The SIS API returns {code, description, formalDescription}
            plan_code = program.get('code')
            is_dept_program = plan_code in plan_codes

            if is_dept_program:
                status = True

            if is_dept_program or show_all:
                details.append({
                    'program': program.get('description'),
                    'status': 'Active',  # SIS doesn't return status for active plans
                    'dept_match': is_dept_program
                })

    return {'status': status, 'details': details}


def _evaluate_courses(flow_results, dept_config, flow_errors, show_all):
    status = None if 'sis_courses' in flow_errors else False
    details = []
    if 'sis_courses' in flow_errors or 'sis_courses' not in flow_results:
        return {'status': status, 'details': details}

    enrollments = flow_results['sis_courses'].get('courses') or []
    subject_areas = _dept_subject_areas(dept_config)

    if isinstance(enrollments, list):
        for enrollment in enrollments:
            if not isinstance(enrollment, dict):
                continue

            # The SIS API can return two different structures:
            # 1. Direct course objects: {subjectArea: {code: "STAT"}, catalogNumber: ...}
            # 2. Nested enrollments: {classSections: [{class: {course: {...}}}]}

            if 'subjectArea' in enrollment:
                subject_area = enrollment.get('subjectArea', {}).get('code')
                catalog_num = enrollment.get('catalogNumber', {}).get('formatted', '')
                is_dept_course = subject_area in subject_areas

                if is_dept_course:
                    status = True

                if is_dept_course or show_all:
                    details.append({
                        'course': f"{subject_area} {catalog_num}".strip(),
                        'title': enrollment.get('title'),
                        'dept_match': is_dept_course
                    })
            elif 'classSections' in enrollment:
                for section in enrollment.get('classSections', []):
                    if not isinstance(section, dict):
                        continue
                    course = section.get('class', {}).get('course', {})
                    subject_area = course.get('subjectArea', {}).get('code')
                    is_dept_course = subject_area in subject_areas

                    if is_dept_course:
                        status = True

                    if is_dept_course or show_all:
                        details.append({
                            'course': f"{subject_area} {course.get('catalogNumber', {}).get('formatted')}",
                            'title': course.get('title'),
                            'dept_match': is_dept_course
                        })

    return {'status': status, 'details': details}


def _evaluate_teaching_staff(flow_results, dept_config, flow_errors, show_all):
    status = None if 'staff_assignments_lookup' in flow_errors else False
    details = []
    if 'staff_assignments_lookup' in flow_errors or 'staff_assignments_lookup' not in flow_results:
        return {'status': status, 'details': details}

    assignments = flow_results['staff_assignments_lookup'].get('assignments') or []
    if isinstance(assignments, dict) and 'assignments' in assignments:
        assignments = assignments.get('assignments', [])
    if not isinstance(assignments, list):
        assignments = []

    subject_areas = _dept_subject_areas(dept_config)

    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        is_dept_assignment = assignment.get('subject_area') in subject_areas

        if is_dept_assignment:
            status = True

        if is_dept_assignment or show_all:
            details.append({
                'course': assignment.get('course'),
                'title': assignment.get('title'),
                'role': assignment.get('role'),
                'component': assignment.get('component'),
                'section_number': assignment.get('section_number'),
                'dept_match': is_dept_assignment
            })

    return {'status': status, 'details': details}


def _evaluate_groups(flow_results, dept_config, flow_errors, show_all):
    status = None if 'grouper_lookup' in flow_errors else False
    details = []
    if 'grouper_lookup' in flow_errors or 'grouper_lookup' not in flow_results:
        return {'status': status, 'details': details}

    grouper_response = flow_results['grouper_lookup'].get('groups') or {}
    folder_prefixes = _dept_folder_prefixes(dept_config)

    # grouper subject --json returns {group_memberships: [...]}
    group_memberships = grouper_response.get('group_memberships', []) if isinstance(grouper_response, dict) else []

    if isinstance(group_memberships, list):
        for group in group_memberships:
            if isinstance(group, str):
                is_dept_group = False
                for prefix in folder_prefixes:
                    if group.startswith(prefix):
                        is_dept_group = True
                        status = True
                        break

                if is_dept_group or show_all:
                    details.append({
                        'name': group,
                        'dept_match': is_dept_group
                    })

    return {'status': status, 'details': details}


def _evaluate_ldap(flow_results, dept_config, flow_errors, show_all):
    status = None if 'dept_ldap_lookup' in flow_errors else False
    if 'dept_ldap_lookup' not in flow_errors and 'dept_ldap_lookup' in flow_results:
        ldap_data = flow_results['dept_ldap_lookup']
        if ldap_data.get('exists'):
            status = True
    return {'status': status, 'details': []}


# Maps a flow step name to the evaluator that turns that step's own
# flow_results entry into an affiliation category. Used both to assemble the
# full determine_affiliations() result and, per step, to let callers (e.g.
# the web app's live-search view) evaluate a single category the moment its
# source finishes, without waiting for the rest of the flow.
STEP_EVALUATORS = {
    'jobs_lookup': _evaluate_employee,
    'sis_plans': _evaluate_student,
    'sis_courses': _evaluate_courses,
    'grouper_lookup': _evaluate_groups,
    'dept_ldap_lookup': _evaluate_ldap,
    'staff_assignments_lookup': _evaluate_teaching_staff,
}


def determine_single_affiliation(step_name: str, flow_results: Dict[str, Any], dept_config: Dict[str, Any], flow_errors: Optional[Dict[str, str]] = None, show_all: bool = False) -> Optional[Dict[str, Any]]:
    """
    Evaluate the single affiliation category driven by one flow step, as
    soon as that step's entry in flow_results is available (i.e. before the
    rest of the flow has necessarily finished).

    Args:
        step_name: Flow step name (e.g. "jobs_lookup"). Steps not in
            STEP_EVALUATORS (identity-resolution steps) return None.
        flow_results: Flow results gathered so far - only this step's own
            entry is read.
        dept_config: Department configuration.
        flow_errors: Dictionary mapping step names to error messages.
        show_all: If True, include non-department-matching detail entries.

    Returns:
        {'status': True/False/None, 'details': [...]}, or None if step_name
        isn't one of the affiliation-driving steps.
    """
    evaluator = STEP_EVALUATORS.get(step_name)
    if evaluator is None:
        return None
    return evaluator(flow_results, dept_config, flow_errors or {}, show_all)


def determine_affiliations(flow_results: Dict[str, Any], dept_config: Dict[str, Any], flow_errors: Optional[Dict[str, str]] = None, show_all: bool = False) -> Dict[str, Any]:
    """
    Determine user's affiliations with the department based on flow results.

    Args:
        flow_results: Results from the flowtoy flow
        dept_config: Department configuration
        flow_errors: Dictionary mapping step names to error messages
        show_all: If True, show all affiliations (not just dept-specific ones)

    Returns:
        Dictionary of affiliations with status (True/False/None for unknown)
    """
    flow_errors = flow_errors or {}

    employee = _evaluate_employee(flow_results, dept_config, flow_errors, show_all)
    student = _evaluate_student(flow_results, dept_config, flow_errors, show_all)
    courses = _evaluate_courses(flow_results, dept_config, flow_errors, show_all)
    teaching_staff = _evaluate_teaching_staff(flow_results, dept_config, flow_errors, show_all)
    groups = _evaluate_groups(flow_results, dept_config, flow_errors, show_all)
    ldap = _evaluate_ldap(flow_results, dept_config, flow_errors, show_all)

    return {
        'employee': employee['status'],
        'student': student['status'],
        'enrolled_in_courses': courses['status'],
        'group_member': groups['status'],
        'ldap_user': ldap['status'],
        'teaching_staff': teaching_staff['status'],
        'errors': flow_errors.copy(),
        'details': {
            'jobs': employee['details'],
            'programs': student['details'],
            'courses': courses['details'],
            'groups': groups['details'],
            'staff_assignments': teaching_staff['details'],
        }
    }
