"""Department lookup from departments.json. The model never supplies
departments, addresses or deadlines (PRD p.5 correctness)."""
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from backend.errors import no_department
from backend.models import Department, Route


class DepartmentRecord(Department):
    """A departments.json entry: the PRD's Department plus matching keys and a
    `verified` flag (False for demo placeholders)."""

    routes: list[Route]
    categories: list[str]  # category names or "*"
    areas: list[str] = Field(default_factory=lambda: ["*"])  # area names or "*"
    verified: bool = False

    def to_department(self) -> Department:
        return Department(**self.model_dump(include=set(Department.model_fields)))


class DepartmentsFile(BaseModel):
    departments: list[DepartmentRecord]

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [d.id for d in self.departments]
        if len(ids) != len(set(ids)):
            raise ValueError("departments.json has duplicate ids")
        return self


class DepartmentLookup:
    def __init__(self, records: list[DepartmentRecord]):
        self._records = records

    @classmethod
    def load(cls, path: Path) -> "DepartmentLookup":
        data = DepartmentsFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        return cls(data.departments)

    def find(
        self, route: Route, category: str, area: Optional[str] = None
    ) -> Optional[DepartmentRecord]:
        """First entry matching route, category and area; exact entries win
        over "*" wildcards."""
        area_n = (area or "").strip().casefold()
        best: Optional[tuple[int, DepartmentRecord]] = None
        for r in self._records:
            if route not in r.routes:
                continue
            if "*" not in r.categories and category not in r.categories:
                continue
            area_exact = area_n and area_n in {a.casefold() for a in r.areas}
            if "*" not in r.areas and not area_exact:
                continue
            score = (0 if "*" in r.categories else 2) + (1 if area_exact else 0)
            if best is None or score > best[0]:
                best = (score, r)
        return best[1] if best else None

    def require(self, route: Route, category: str, area: Optional[str] = None) -> DepartmentRecord:
        found = self.find(route, category, area)
        if found is None:
            raise no_department()
        return found

    def unverified_ids(self) -> list[str]:
        """Entries not marked verified (demo placeholders). Their names,
        addresses and response_days must not be shown as official."""
        return [r.id for r in self._records if not r.verified]

    def get(self, department_id: str) -> Optional[DepartmentRecord]:
        return next((r for r in self._records if r.id == department_id), None)
