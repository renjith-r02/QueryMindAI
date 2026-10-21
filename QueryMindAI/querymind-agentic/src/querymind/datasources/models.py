"""Data sources QueryMind can query, with the documentation the model uses to write SQL.

Connection details never include passwords or keys; credentials stay in the server
configuration (QUERYMIND_DB_<NAME>).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DataSourceType = Literal["mysql", "postgresql", "cassandra", "dynamodb"]

#: Allowed connection fields per type (no secrets: credentials stay in server config).
CONNECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "mysql": ("host", "port", "database", "username"),
    "postgresql": ("host", "port", "database", "schema", "username"),
    "cassandra": ("contact_points", "port", "keyspace", "datacenter", "username"),
    "dynamodb": ("region", "tables", "endpoint"),
}

#: Documentation sections, in the order and wording of the annotated schema files.
SECTION_KEYS: tuple[str, ...] = (
    "purpose",
    "data_location_map",
    "table_overview",
    "relationships",
    "entity_diagram",
    "join_paths",
    "returns_questions",
    "business_rules",
)
SectionKey = Literal[
    "purpose",
    "data_location_map",
    "table_overview",
    "relationships",
    "entity_diagram",
    "join_paths",
    "returns_questions",
    "business_rules",
]

MAX_SECTION_CHARS = 20_000
MAX_CONNECTION_VALUE_CHARS = 500


class DataSourceInput(BaseModel):
    """What a client may set. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: DataSourceType
    enabled: bool = True
    connection: dict[str, str] = Field(default_factory=dict, description="Allowed keys depend on type; no secrets")
    sections: dict[SectionKey, str] = Field(default_factory=dict, description="Documentation, by section")

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value or "\n" in value:
            raise ValueError("name must be a non-empty single line")
        return value

    @field_validator("sections")
    @classmethod
    def _sections(cls, value: dict[str, str]) -> dict[str, str]:
        for key, text in value.items():
            if len(text) > MAX_SECTION_CHARS:
                raise ValueError(f"section {key} is longer than {MAX_SECTION_CHARS} characters")
        return value

    @model_validator(mode="after")
    def _connection_matches_type(self) -> DataSourceInput:
        allowed = CONNECTION_FIELDS[self.type]
        unknown = sorted(set(self.connection) - set(allowed))
        if unknown:
            raise ValueError(f"connection fields {unknown} are not used by {self.type}; allowed: {list(allowed)}")
        for key, text in self.connection.items():
            if len(text) > MAX_CONNECTION_VALUE_CHARS or "\n" in text or "\r" in text:
                raise ValueError(f"connection.{key} must be a single line of at most {MAX_CONNECTION_VALUE_CHARS}")
        self.connection = {key: text.strip() for key, text in self.connection.items()}
        return self


class DataSource(DataSourceInput):
    """A stored data source."""

    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: float
    updated_at: float
    #: "qdrant": saved in settings; "env": only configured as QUERYMIND_DB_<NAME> in .env (id "env:<name>").
    origin: Literal["qdrant", "env"] = "qdrant"
