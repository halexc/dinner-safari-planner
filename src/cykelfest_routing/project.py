"""Versioned JSON dinner-safari project files (.dsf)."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .data import DinnerData, Participant, Route, Stop
from .verification import WARNING_TYPES


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    safe_edit: bool = Field(default=True, strict=True)
    minimum_segment_km: float = Field(default=0.5, ge=0, le=1000, multiple_of=0.01)
    maximum_segment_km: float = Field(default=3, ge=0, le=1000, multiple_of=0.01)
    ignored_warnings: set[str] = Field(default_factory=set)
    minimize_warning_counts: dict[str, Annotated[bool, Field(strict=True)]] = Field(
        default_factory=lambda: dict.fromkeys(WARNING_TYPES, True)
    )
    respect_existing_routes: bool = Field(default=False, strict=True)
    warning_multipliers: dict[str, Annotated[float, Field(ge=0, le=5, multiple_of=0.001)]] = Field(
        default_factory=lambda: dict.fromkeys(WARNING_TYPES, 1.0)
    )

    @model_validator(mode="after")
    def ordered_lengths(self):
        if self.minimum_segment_km > self.maximum_segment_km:
            raise ValueError("Minimum segment length must not exceed maximum length.")
        if self.ignored_warnings - set(WARNING_TYPES):
            raise ValueError("Unknown warning type in project settings.")
        if self.warning_multipliers.keys() - set(WARNING_TYPES):
            raise ValueError("Unknown warning type in penalty multipliers.")
        if self.minimize_warning_counts.keys() - set(WARNING_TYPES):
            raise ValueError("Unknown warning type in warning minimization settings.")
        self.minimize_warning_counts = (
            dict.fromkeys(WARNING_TYPES, True) | self.minimize_warning_counts
        )
        self.warning_multipliers = dict.fromkeys(WARNING_TYPES, 1.0) | self.warning_multipliers
        return self


class ProjectFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["cykelfest-dinner-safari"]
    version: Literal[2]
    participants: list[Participant]
    stops: list[Stop]
    routes: list[Route]
    settings: ProjectSettings

    @model_validator(mode="after")
    def relationships(self):
        for kind in ("participants", "stops", "routes"):
            ids = [record.id for record in getattr(self, kind)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate IDs in {kind}.")
        linked = [p.route_id for p in self.participants if p.route_id]
        if len(linked) != len(set(linked)) or set(linked) != {r.id for r in self.routes}:
            raise ValueError("Every route must link to exactly one distinct participant.")
        return self


def save_project(path, data, settings):
    project = ProjectFile(
        format="cykelfest-dinner-safari",
        version=2,
        participants=list(data.participants.values()),
        stops=list(data.stops.values()),
        routes=list(data.routes.values()),
        settings=settings,
    )
    destination = Path(path)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(project.model_dump_json(indent=2))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_project(path):
    content = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if (
        not isinstance(content, dict)
        or type(content.get("version")) is not int
        or content["version"] not in (1, 2)
    ):
        raise ValueError("Unsupported or missing project version (expected 1 or 2).")
    if content["version"] == 1:
        content["version"] = 2
        if isinstance(content.get("settings"), dict):
            for key in ("dark_mode", "verify_on_change", "csv_delimiter"):
                content["settings"].pop(key, None)
    project = ProjectFile.model_validate(content)
    data = DinnerData()
    for kind in ("participants", "stops", "routes"):
        setattr(data, kind, {record.id: record for record in getattr(project, kind)})
    return data, project.settings
