"""Which FOCUS data a tool call reads, and the DuckDB connection that reads it.

A call names its data with a *dataset handle* and a FOCUS version. Handles
are opaque names: the catalog turns them into a storage location, so the
model never has to know (or be allowed to name) a bucket. Resolution order:

1. No handle: the process default (FOCUS_DATA_LOCATION / FOCUS_VERSION).
2. A name in FOCUS_DATASETS: the static map, for self-hosted setups.
3. FOCUS_CATALOG_URL: an HTTP lookup that carries the caller's bearer token,
   so a shared server can serve many tenants from one process and the
   catalog decides what each token may read.
4. A raw location (s3://..., /path): only when raw locations are allowed —
   always over stdio, where the client already is the local user; over HTTP
   only with FOCUS_ALLOW_RAW_LOCATIONS, because there the handle travels in
   a header any intermediary can see.

Connections are pooled per resolved location. A location's view is rebuilt
after VIEW_MAX_AGE_SECONDS so later deliveries show up, and the least
recently used connection is closed once the pool is full.
"""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import duckdb

from . import config
from .data_loading import create_focus_view
from .storage_backends import resolve_backend

logger = logging.getLogger(__name__)

# The manifest strategy pins the file list of one delivery, so a server that
# stays up for days has to rebuild the view to see the deliveries after it.
VIEW_MAX_AGE_SECONDS = 300

# Catalog answers are cached briefly so a chat's burst of tool calls costs
# one lookup, while a revoked token stops working within the minute.
CATALOG_CACHE_SECONDS = 60


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


def _normalize_version(version: Optional[str], fallback: str) -> str:
    return str(version).lstrip("v") if version else fallback


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
        catalog_url: Optional[str] = None,
        allow_raw_locations: Optional[bool] = None,
        http_client=None,
    ):
        self.default_location = config.DATA_LOCATION if default_location is None else default_location
        self.default_version = config.FOCUS_VERSION if default_version is None else default_version
        self.datasets = dict(config.DATASETS if datasets is None else datasets)
        self.catalog_url = (config.CATALOG_URL if catalog_url is None else catalog_url).rstrip("/")
        self.allow_raw_locations = config.ALLOW_RAW_LOCATIONS if allow_raw_locations is None else allow_raw_locations
        self._http_client = http_client
        self._remote_cache: dict[tuple[str, str], tuple[float, Dataset]] = {}

    def resolve(
        self,
        handle: Optional[str] = None,
        version: Optional[str] = None,
        *,
        token: Optional[str] = None,
    ) -> Dataset:
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

        if self.catalog_url:
            remote = self._resolve_remote(handle, token)
            return Dataset(
                remote.location,
                _normalize_version(version, remote.version or self.default_version),
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

    def _resolve_remote(self, handle: str, token: Optional[str]) -> Dataset:
        key = (token or "", handle)
        cached = self._remote_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        import httpx

        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        client = self._http_client or httpx
        try:
            response = client.get(
                f"{self.catalog_url}/{quote(handle, safe='')}",
                headers=headers,
                timeout=10.0,
            )
        except Exception as e:
            raise DatasetError(f"Dataset catalog unreachable: {e}") from e

        if response.status_code == 404:
            raise DatasetError(f"Unknown dataset {handle!r}.")
        if response.status_code in (401, 403):
            raise DatasetError(f"Not allowed to read dataset {handle!r}.")
        if response.status_code >= 400:
            raise DatasetError(f"Dataset catalog returned HTTP {response.status_code} for {handle!r}.")

        body = response.json()
        location = body.get("location") if isinstance(body, dict) else None
        if not location:
            raise DatasetError(f"Dataset catalog returned no location for {handle!r}.")
        dataset = Dataset(str(location), str(body.get("version") or "").lstrip("v"), handle)
        self._remote_cache[key] = (time.monotonic() + CATALOG_CACHE_SECONDS, dataset)
        return dataset


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
    """One prepared DuckDB connection per location, least recently used evicted."""

    def __init__(self, max_size: Optional[int] = None):
        self.max_size = max(1, config.MAX_DATASETS if max_size is None else max_size)
        self._entries: "OrderedDict[str, Connection]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, location: str) -> Connection:
        # Keyed on the normalized form so "s3://b/p" and "s3://b/p/" share
        # one connection instead of loading the same data twice.
        location = resolve_backend(location).normalize(location).rstrip("/")
        with self._lock:
            entry = self._entries.get(location)
            if entry is None:
                entry = self._open(location)
                self._entries[location] = entry
                while len(self._entries) > self.max_size:
                    _, evicted = self._entries.popitem(last=False)
                    evicted.conn.close()
            else:
                self._entries.move_to_end(location)
                if entry.strategy and time.monotonic() - entry.built_at > VIEW_MAX_AGE_SECONDS:
                    self._refresh(entry)
            return entry

    def _open(self, location: str) -> Connection:
        conn = duckdb.connect()
        backend = resolve_backend(location)
        # prepare() loads extensions and credentials and returns an error
        # hint to surface if reads fail later.
        hint = backend.prepare(conn, location)

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
                    raise RuntimeError(hint) from e
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
