"""Flowtoy provider that finds SIS class sections where a person is teaching staff.

Queries the SIS Classes API for the configured subject areas in a term and
returns the sections where the input campus UID appears among the assigned
instructors, either as instructor (role PI) or as teaching assistant/GSI
(role TNIC).
"""
import asyncio
import os
from typing import Any, Dict, List, Optional

import yaml

from sis import sis as sis_api
from sis import terms as sis_terms

SECTIONS_URI = "https://gateway.api.berkeley.edu/sis/v1/classes/sections"
ROLE_LABELS = {
    "PI": "Instructor",
    "TNIC": "Teaching Assistant",
}
PAGE_SIZE = 400


def _read_credentials() -> Dict[str, Any]:
    """Read SIS credentials from SIS_* environment variables."""
    creds: Dict[str, Any] = {}
    for key in ("classes_id", "classes_key", "terms_id", "terms_key"):
        env_key = f"SIS_{key.upper()}"
        if env_key in os.environ:
            creds[key] = os.environ[env_key]
    return creds


class StaffCoursesProvider:
    """Find sections where the input UID is assigned as teaching staff."""

    type_name = "staff_courses"

    def __init__(self, configuration: Dict[str, Any]):
        self.configuration = configuration or {}
        self.subject_areas: List[str] = self.configuration.get("subject_areas") or []
        self.term = str(self.configuration.get("term") or "Current")

    def _resolve_term_id(self, creds: Dict[str, Any]) -> str:
        if self.term.isdigit():
            return self.term
        term_id = asyncio.run(
            sis_terms.get_term_id(
                creds["terms_id"], creds["terms_key"], self.term.capitalize()
            )
        )
        if not term_id:
            raise Exception(f"No SIS term found for position '{self.term}'")
        return str(term_id)

    def _subject_areas_from_dept_config(self) -> List[str]:
        """Fall back to the department config's course subject areas.

        The CLI/web app set UCB_AFFILIATIONS_CONFIG to whichever config
        file they were actually told to use (--config / create_app's
        config_file) - this provider is instantiated generically by
        flowtoy from the flow YAML, with no other channel to learn that.
        """
        config_path = os.environ.get("UCB_AFFILIATIONS_CONFIG", "config.yaml")
        try:
            with open(config_path) as f:
                dept_config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            return []
        if "courses" in dept_config:
            return dept_config["courses"].get("subject_areas", [])
        return dept_config.get("department", {}).get("course_subject_areas", [])

    def _section_assignments(self, section: Dict[str, Any], uid: str) -> List[Dict[str, Any]]:
        course = section.get("class", {}).get("course", {})
        subject_area = (course.get("subjectArea") or {}).get("code")
        catalog_number = ((course.get("catalogNumber") or {}).get("formatted")) or ""
        found = []
        for meeting in section.get("meetings") or []:
            for assigned in meeting.get("assignedInstructors") or []:
                instructor = assigned.get("instructor") or {}
                uids = {
                    str(i.get("id"))
                    for i in (instructor.get("identifiers") or [])
                    if i.get("type") == "campus-uid"
                }
                if str(uid) not in uids:
                    continue
                role = assigned.get("role") or {}
                code = role.get("code")
                found.append({
                    "subject_area": subject_area,
                    "course": f"{subject_area or ''} {catalog_number}".strip(),
                    "title": course.get("title"),
                    "section_number": section.get("number"),
                    "component": (section.get("component") or {}).get("description"),
                    "role_code": code,
                    "role": ROLE_LABELS.get(code, role.get("description") or code),
                })
        return found

    def _lookup(self, uid: Any) -> List[Dict[str, Any]]:
        if uid is None or str(uid).strip() == "":
            raise Exception("no campus uid provided")
        uid = str(uid)

        if not self.subject_areas:
            self.subject_areas = self._subject_areas_from_dept_config()
        if not self.subject_areas:
            raise Exception("no subject_areas configured")

        creds = _read_credentials()
        missing = [k for k in ("classes_id", "classes_key") if not creds.get(k)]
        if missing:
            raise Exception(f"missing SIS credentials: {', '.join(missing)}")

        term_id = self._resolve_term_id(creds)
        headers = {
            "Accept": "application/json",
            "app_id": creds["classes_id"],
            "app_key": creds["classes_key"],
        }

        assignments: List[Dict[str, Any]] = []
        seen = set()
        for area in self.subject_areas:
            params = {
                "subject-area-code": str(area).upper(),
                "term-id": term_id,
                "include-secondary": "true",
                "page-size": PAGE_SIZE,
                "page-number": 1,
            }
            sections = asyncio.run(
                sis_api.get_items(SECTIONS_URI, params, headers, "classSections")
            )
            for section in sections:
                for assignment in self._section_assignments(section, uid):
                    key = (
                        assignment.get("course"),
                        assignment.get("section_number"),
                        assignment.get("role_code"),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    assignments.append(assignment)
        return assignments

    def call(self, input_payload: Optional[Any] = None) -> Dict[str, Any]:
        try:
            data = self._lookup(input_payload)
            return {
                "status": {"success": True, "code": 0, "notes": []},
                "data": {"assignments": data},
                "meta": {},
            }
        except Exception as e:
            return {
                "status": {"success": False, "code": 1, "notes": [str(e)]},
                "data": None,
                "meta": {},
            }
