"""Derives ChunkSchema metadata fields from a source file's folder path.

Company KB layout:
    data/company_kb/departments/<department>/<category>/<topic>.txt
    data/company_kb/departments/<department>/department_overview.txt

Project KB layout (mirrors it):
    data/project_kb/projects/<project>/<category>/<topic>.txt

This is what lets Salma/Doha's parsers tag every chunk correctly with
zero manual labeling -- the folder position *is* the metadata.
"""

from pathlib import Path
from typing import TypedDict


class CompanyKbPathInfo(TypedDict):
    department: str
    category: str
    topic: str


def parse_company_kb_path(file_path: str) -> CompanyKbPathInfo:
    """
    Example: data/company_kb/departments/software/roles/backend_engineer.txt
             -> department="software", category="roles", topic="backend_engineer"

    Example: data/company_kb/departments/software/department_overview.txt
             -> department="software", category="overview", topic="department_overview"
    """
    p = Path(file_path)
    parts = p.parts

    dept_idx = parts.index("departments") + 1
    department = parts[dept_idx]

    remainder = parts[dept_idx + 1:]
    topic = p.stem

    if len(remainder) == 1:
        # file sits directly under the department folder, e.g. department_overview.txt
        category = "overview"
    else:
        category = remainder[0]

    return {"department": department, "category": category, "topic": topic}


class ProjectKbPathInfo(TypedDict):
    project: str
    category: str
    topic: str


def parse_project_kb_path(file_path: str) -> ProjectKbPathInfo:
    """
    Example: data/project_kb/projects/payment-platform/apis/refund_api.txt
             -> project="payment-platform", category="apis", topic="refund_api"
    """
    p = Path(file_path)
    parts = p.parts

    proj_idx = parts.index("projects") + 1
    project = parts[proj_idx]

    remainder = parts[proj_idx + 1:]
    topic = p.stem
    category = remainder[0] if len(remainder) > 1 else "overview"

    return {"project": project, "category": category, "topic": topic}
