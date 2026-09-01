"""Which FOCUS data a tool call reads, and the DuckDB connection that reads it.

A call names its data with a *dataset handle* and a FOCUS version. Handles
are opaque names, so the model never has to know (or be allowed to name) a
bucket. Resolution order:

1. Datasets sent with the request (X-Focus-Datasets): over HTTP the client
   says what it may read and, with X-Aws-* headers, proves it with its own
   AWS keys. One shared server then serves many tenants without holding
   any of their credentials or configuration.
2. No handle: the process default (FOCUS_DATA_LOCATION / FOCUS_VERSION).
3. A name in FOCUS_DATASETS: the static map, for self-hosted setups.
4. A raw location (s3://..., /path): only when raw locations are allowed —
   always over stdio, where the client already is the local user; over HTTP
   only with FOCUS_ALLOW_RAW_LOCATIONS, because there the handle travels in
   a header any intermediary can see.

Connections are pooled per resolved location and credential. A location's
view is rebuilt after VIEW_MAX_AGE_SECONDS so later deliveries show up, and
the least recently used connection is closed once the pool is full.
"""

import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Mapping, Optional

import duckdb

from . import config
from .data_loading import create_focus_view
from .storage_backends import resolve_backend

logger = logging.getLogger(__name__)

# The manifest strategy pins the file list of one delivery, so a server that
# stays up for days has to rebuild the view to see the deliveries after it.
VIEW_MAX_AGE_SECONDS = 300

DATASETS_HEADER = "x-focus-datasets"
VERSION_HEADER = "x-focus-version"
CREDENTIAL_HEADERS = {
    "key_id": "x-aws-access-key-id",
    "secret": "x-aws-secret-access-key",
    "session_token": "x-aws-session-token",
    "region": "x-aws-region",
}

HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class DatasetError(Exception):
    """The dataset could not be resolved; the message is safe to show a client."""


@dataclass(frozen=True)
class Dataset:
    location: str
    version: str
    handle: Optional[str] = None

    @property
    def label(self) -> str:
        return self.handle or self.location


@dataclass(frozen=True)
class Credentials:
    """AWS keys a request brought along; they are used for that request only."""

    key_id: str
    secret: str
    session_token: str = ""
    region: str = ""

    def __repr__(self) -> str:
        return f"Credentials(key_id={self.key_id!r})"


@dataclass(frozen=True)
class RequestScope:
    """What one request may read: its datasets, in order, and how to reach them."""

    datasets: dict[str, Dataset]
    credentials: Optional[Credentials] = None

    @property
    def default(self) -> Optional[str]:
        return next(iter(self.datasets), None)

    @classmethod
    def from_headers(cls, headers: Optional[Mapping[str, str]], default_version: str) -> "RequestScope":
        """Parse X-Focus-Datasets / X-Focus-Version / X-Aws-* headers.

        X-Focus-Datasets is a comma-separated list of ``name=location`` pairs,
        optionally ``name=location@version``; the first entry is the default
        dataset. Header names are matched case-insensitively.
        """
        if not headers:
            return cls({})
        lowered = {str(k).lower(): v for k, v in headers.items()}
        version = _normalize_version(lowered.get(VERSION_HEADER), default_version)
        datasets: dict[str, Dataset] = {}
        for item in lowered.get(DATASETS_HEADER, "").split(","):
            item = item.strip()
            if not item:
                continue
            name, sep, target = item.partition("=")
            name = name.strip()
            if not sep or not HANDLE_RE.match(name):
                raise DatasetError(
                    f"{DATASETS_HEADER} entries look like name=location; {item!r} does not."
                )
            location, _, entry_version = target.strip().partition("@")
            if not looks_like_location(location):
                raise DatasetError(f"Dataset {name!r} has no readable location.")
            datasets[name] = Dataset(
                config._resolve_location(location),
                _normalize_version(entry_version, version),
                name,
            )

        credentials = None
        key_id = lowered.get(CREDENTIAL_HEADERS["key_id"], "").strip()
        secret = lowered.get(CREDENTIAL_HEADERS["secret"], "").strip()
        if key_id or secret:
            if not (key_id and secret):
                raise DatasetError("AWS credentials need both an access key id and a secret.")
            credentials = Credentials(
                key_id,
                secret,
                lowered.get(CREDENTIAL_HEADERS["session_token"], "").strip(),
                lowered.get(CREDENTIAL_HEADERS["region"], "").strip(),
            )
        return cls(datasets, credentials)


def _normalize_version(version: Optional[str], fallback: str) -> str:
    return str(version).strip().lstrip("v") if version and str(version).strip() else fallback


def looks_like_location(value: str) -> bool:
    return "://" in value or value.startswith("/") or value.startswith("~")


class Catalog:
    """Resolves dataset handles for the running process."""

    # Configuration is read when the catalog is built, not when this module
    # is imported, so a process that reconfigures and rebuilds sees its
    # current environment.
    def __init__(
        self,
        *,
        default_location: Optional[str] = None,
        default_version: Optional[str] = None,
        datasets: Optional[dict[str, dict[str, str]]] = None,
        allow_raw_locations: Optional[bool] = None,
    ):
        self.default_location = config.DATA_LOCATION if default_location is None else default_location
        self.default_version = config.FOCUS_VERSION if default_version is None else default_version
        self.datasets = dict(config.DATASETS if datasets is None else datasets)
        self.allow_raw_locations = config.ALLOW_RAW_LOCATIONS if allow_raw_locations is None else allow_raw_locations

    def scope(self, headers: Optional[Mapping[str, str]]) -> RequestScope:
        return RequestScope.from_headers(headers, self.default_version)

    def resolve(
        self,
        handle: Optional[str] = None,
        version: Optional[str] = None,
        *,
        scope: Optional[RequestScope] = None,
    ) -> Dataset:
        # A request that brought its own datasets reads those and nothing
        # else: the process default and the static map belong to the host.
        if scope and scope.datasets:
            name = handle or scope.default
            entry = scope.datasets.get(name)
            if entry is None:
                raise DatasetError(
                    f"Unknown dataset {handle!r}. This request may read: {', '.join(scope.datasets)}."
                )
            return Dataset(entry.location, _normalize_version(version, entry.version), name)

        if not handle:
            return Dataset(
                self.default_location,
                _normalize_version(version, self.default_version),
            )

        entry = self.datasets.get(handle)
        if entry is not None:
            return Dataset(
                entry["location"],
                _normalize_version(version, entry.get("version") or self.default_version),
                handle,
            )

        if self.allow_raw_locations and looks_like_location(handle):
            return Dataset(
                config._resolve_location(handle),
                _normalize_version(version, self.default_version),
                handle,
            )

        known = ", ".join(sorted(self.datasets)) or "none"
        raise DatasetError(f"Unknown dataset {handle!r}. Known datasets: {known}.")


@dataclass
class Connection:
    conn: duckdb.DuckDBPyConnection
    location: str
    # How focus_data_table was built: "manifest" reads an export's own
    # delivery manifests, the glob strategies read every Parquet file under
    # the location. None means no data was found.
    strategy: Optional[str]
    built_at: float


class ConnectionPool:
    """One prepared DuckDB connection per (location, credential), least recently used evicted."""

    def __init__(self, max_size: Optional[int] = None):
        self.max_size = max(1, config.MAX_DATASETS if max_size is None else max_size)
        self._entries: "OrderedDict[tuple[str, str], Connection]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, location: str, credentials: Optional[Credentials] = None) -> Connection:
        # Keyed on the normalized form so "s3://b/p" and "s3://b/p/" share
        # one connection instead of loading the same data twice. Rotated
        # keys get a fresh connection; the old one ages out of the pool.
        location = resolve_backend(location).normalize(location).rstrip("/")
        key = (location, credentials.key_id if credentials else "")
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = self._open(location, credentials)
                self._entries[key] = entry
                while len(self._entries) > self.max_size:
                    _, evicted = self._entries.popitem(last=False)
                    evicted.conn.close()
            else:
                self._entries.move_to_end(key)
                if entry.strategy and time.monotonic() - entry.built_at > VIEW_MAX_AGE_SECONDS:
                    self._refresh(entry)
            return entry

    def _open(self, location: str, credentials: Optional[Credentials]) -> Connection:
        conn = duckdb.connect()
        backend = resolve_backend(location)
        # prepare() loads extensions and credentials and returns an error
        # hint to surface if reads fail later.
        hint = backend.prepare(conn, location, credentials)

        strategy = None
        if backend.exists(location):
            try:
                strategy = create_focus_view(conn, location)
            except Exception as e:
                # Nothing is cached on failure, so the next call retries and
                # raises again instead of handing out a viewless connection
                # that fails with a catalog error.
                conn.close()
                if hint:
                    raise RuntimeError(f"{e} ({hint})") from e
                raise
        return Connection(conn, location, strategy, time.monotonic())

    def _refresh(self, entry: Connection) -> None:
        # A failed refresh keeps the working view in place and is retried
        # after the next interval: a transient listing failure must not take
        # down a server that is serving data fine.
        entry.built_at = time.monotonic()
        try:
            entry.strategy = create_focus_view(entry.conn, entry.location)
        except Exception as e:
            logger.warning("Keeping the loaded data: reloading it from %s failed: %s", entry.location, e)

    def close_all(self) -> None:
        with self._lock:
            for entry in self._entries.values():
                entry.conn.close()
            self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
