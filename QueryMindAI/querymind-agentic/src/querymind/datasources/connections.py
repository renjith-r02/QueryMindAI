"""Decide how to connect to each database: saved data source first, the .env file as fallback.

For every database name (a data source name, or <NAME> in QUERYMIND_DB_<NAME>):
  * no saved data source            -> the QUERYMIND_DB_<NAME> URL from .env, as before;
  * saved and disabled              -> not queried at all;
  * saved MySQL / PostgreSQL source -> its host, port, database and user; any empty field
                                       falls back to the .env URL; the password always comes
                                       from the .env URL (passwords are never stored in Qdrant);
  * saved but unusable (incomplete, or a type the executor can't query yet) -> the .env URL if
                                       there is one, otherwise not queried.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from querymind.database.executor import ENV_PREFIX
from querymind.datasources.models import DataSource

#: SQLAlchemy drivers used when a saved data source has no .env URL to borrow one from.
DRIVERS = {"mysql": "mysql+pymysql", "postgresql": "postgresql+psycopg"}


@dataclass
class Resolution:
    urls: dict[str, str] = field(default_factory=dict)  # name -> SQLAlchemy URL (with password)
    origins: dict[str, str] = field(default_factory=dict)  # name -> "settings" | "env"
    notes: list[str] = field(default_factory=list)  # why a database was skipped or fell back


def env_database_urls(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """QUERYMIND_DB_<NAME>=<url> entries, keyed by lower-case name."""
    environ = os.environ if environ is None else environ
    return {
        key[len(ENV_PREFIX) :].lower(): value for key, value in environ.items() if key.startswith(ENV_PREFIX) and value
    }


def env_key(name: str) -> str:
    """The .env variable that holds a database's URL, e.g. QUERYMIND_DB_RETURNS_DB."""
    return ENV_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", name).upper()


def connection_from_url(url: str) -> tuple[str, dict[str, str]] | None:
    """(type, connection fields) described by a SQLAlchemy URL; None for unsupported databases."""
    try:
        parsed = make_url(url)
    except ArgumentError:
        return None
    kind = parsed.get_backend_name()
    if kind not in DRIVERS:
        return None
    connection = {
        "host": parsed.host or "",
        "port": str(parsed.port) if parsed.port else "",
        "database": parsed.database or "",
        "username": parsed.username or "",
    }
    return kind, {key: value for key, value in connection.items() if value}


def resolve(stored: Iterable[DataSource], env: Mapping[str, str]) -> Resolution:
    result = Resolution()
    by_name = {source.name.lower(): source for source in stored}
    for name in sorted(set(env) | set(by_name)):
        source, env_url = by_name.get(name), env.get(name)
        if source is None:
            result.urls[name], result.origins[name] = env_url, "env"
            continue
        if not source.enabled:
            result.notes.append(f"{name}: disabled in settings, so it is not queried.")
            continue
        url, problem = _url_for(source, env_url)
        if url is not None:
            result.urls[name], result.origins[name] = url, "settings"
        elif env_url:
            result.urls[name], result.origins[name] = env_url, "env"
            result.notes.append(f"{name}: {problem}; using {env_key(name)} from .env.")
        else:
            result.notes.append(f"{name}: {problem}, and {env_key(name)} is not set.")
    return result


def _url_for(source: DataSource, env_url: str | None) -> tuple[str | None, str]:
    """The URL for a saved data source, or (None, reason)."""
    if source.type not in DRIVERS:
        return None, f"{source.type} data sources can't be queried yet"
    env = None
    if env_url:
        try:
            parsed = make_url(env_url)
            env = parsed if parsed.get_backend_name() == source.type else None
        except ArgumentError:
            env = None

    conn = source.connection
    host = conn.get("host") or (env.host if env else None)
    database = conn.get("database") or (env.database if env else None)
    if not host or not database:
        return None, "the saved settings have no host or database"
    port_text = conn.get("port") or (str(env.port) if env and env.port else "")
    if port_text and not port_text.isdigit():
        return None, f"the saved port {port_text!r} is not a number"

    query = {}
    schema = conn.get("schema")
    if source.type == "postgresql" and schema and schema != "public":
        query["options"] = f"-csearch_path={schema},public"
    url = URL.create(
        env.drivername if env else DRIVERS[source.type],
        username=conn.get("username") or (env.username if env else None),
        password=env.password if env else None,  # never stored in Qdrant
        host=host,
        port=int(port_text) if port_text else None,
        database=database,
        query=query,
    )
    return url.render_as_string(hide_password=False), ""
