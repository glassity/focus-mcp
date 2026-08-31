"""Dataset handles resolve to locations the caller is allowed to read.

Over stdio the client is the local user, so a raw path is fine. Over HTTP a
handle travels in a header any intermediary can see, so only names the
server (or its catalog) knows are honoured, and the catalog answers for the
bearer token rather than for whoever typed the name.
"""

import pytest

from focus_mcp import datasets
from focus_mcp.datasets import Catalog, Dataset, DatasetError


def make_catalog(**overrides):
    defaults = dict(
        default_location="/srv/focus/default",
        default_version="1.0",
        datasets={},
        catalog_url="",
        allow_raw_locations=False,
    )
    defaults.update(overrides)
    return Catalog(**defaults)


def test_no_handle_means_the_process_default():
    assert make_catalog().resolve() == Dataset("/srv/focus/default", "1.0")


def test_version_override_applies_to_the_default_and_drops_the_v_prefix():
    assert make_catalog().resolve(version="v1.2").version == "1.2"


def test_static_datasets_resolve_by_name_with_their_own_version():
    catalog = make_catalog(datasets={"prod": {"location": "s3://lake/focus/prod", "version": "1.2"}})
    assert catalog.resolve("prod") == Dataset("s3://lake/focus/prod", "1.2", "prod")
    # an explicit version still wins over the dataset's own
    assert catalog.resolve("prod", "1.1").version == "1.1"


def test_static_dataset_without_a_version_uses_the_default():
    catalog = make_catalog(datasets={"lab": {"location": "/data/lab", "version": ""}})
    assert catalog.resolve("lab").version == "1.0"


def test_unknown_handle_names_what_exists():
    catalog = make_catalog(datasets={"prod": {"location": "s3://x", "version": ""}, "dev": {"location": "s3://y", "version": ""}})
    with pytest.raises(DatasetError, match="Unknown dataset 'nope'. Known datasets: dev, prod"):
        catalog.resolve("nope")


def test_raw_locations_are_refused_unless_allowed():
    with pytest.raises(DatasetError, match="Unknown dataset"):
        make_catalog().resolve("s3://someone-elses-bucket/focus")

    allowed = make_catalog(allow_raw_locations=True)
    assert allowed.resolve("s3://my-bucket/focus").location == "s3://my-bucket/focus"
    assert allowed.resolve("/tmp/focus").location == "/tmp/focus"


def test_allowing_raw_locations_does_not_make_names_into_paths():
    with pytest.raises(DatasetError, match="Unknown dataset"):
        make_catalog(allow_raw_locations=True).resolve("prod")


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.responses.pop(0)


def test_remote_catalog_forwards_the_bearer_token_and_caches_the_answer(monkeypatch):
    http = FakeHttp([FakeResponse(200, {"location": "s3://lake/focus/t-7/aws-1", "version": "1.2"})])
    catalog = make_catalog(catalog_url="https://app.example/api/focus/datasets/", http_client=http)

    first = catalog.resolve("aws-1", token="tok")
    second = catalog.resolve("aws-1", token="tok")

    assert first == second == Dataset("s3://lake/focus/t-7/aws-1", "1.2", "aws-1")
    assert http.calls == [
        ("https://app.example/api/focus/datasets/aws-1", {"Accept": "application/json", "Authorization": "Bearer tok"})
    ]


def test_remote_catalog_answers_are_per_token():
    http = FakeHttp([
        FakeResponse(200, {"location": "s3://lake/focus/t-7/all"}),
        FakeResponse(200, {"location": "s3://lake/focus/t-9/all"}),
    ])
    catalog = make_catalog(catalog_url="https://app.example/catalog", http_client=http)
    assert catalog.resolve("all", token="seven").location.endswith("t-7/all")
    assert catalog.resolve("all", token="nine").location.endswith("t-9/all")


def test_remote_catalog_cache_expires(monkeypatch):
    http = FakeHttp([FakeResponse(200, {"location": "s3://a"}), FakeResponse(200, {"location": "s3://b"})])
    catalog = make_catalog(catalog_url="https://app.example/catalog", http_client=http)
    clock = [1000.0]
    monkeypatch.setattr(datasets.time, "monotonic", lambda: clock[0])
    assert catalog.resolve("x", token="t").location == "s3://a"
    clock[0] += datasets.CATALOG_CACHE_SECONDS + 1
    assert catalog.resolve("x", token="t").location == "s3://b"


@pytest.mark.parametrize(
    "status, message",
    [(404, "Unknown dataset 'x'"), (401, "Not allowed to read dataset 'x'"), (403, "Not allowed"), (500, "HTTP 500")],
)
def test_remote_catalog_errors_are_explained(status, message):
    catalog = make_catalog(catalog_url="https://app.example/catalog", http_client=FakeHttp([FakeResponse(status)]))
    with pytest.raises(DatasetError, match=message):
        catalog.resolve("x", token="t")


def test_remote_catalog_without_a_location_is_an_error():
    catalog = make_catalog(catalog_url="https://app.example/catalog", http_client=FakeHttp([FakeResponse(200, {})]))
    with pytest.raises(DatasetError, match="no location"):
        catalog.resolve("x")


def test_static_names_win_over_the_remote_catalog():
    http = FakeHttp([])
    catalog = make_catalog(
        datasets={"local": {"location": "/data/local", "version": ""}},
        catalog_url="https://app.example/catalog",
        http_client=http,
    )
    assert catalog.resolve("local").location == "/data/local"
    assert http.calls == []
