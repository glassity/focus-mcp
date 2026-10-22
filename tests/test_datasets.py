"""Dataset handles resolve to locations the caller is allowed to read.

Over stdio the client is the local user, so a raw path is fine. Over HTTP a
handle travels in a header any intermediary can see, so only names the
server knows - or names the request itself declared, backed by the keys it
sent - are honoured.
"""

import pytest

from focus_mcp.datasets import (
    Catalog,
    Credentials,
    Dataset,
    DatasetError,
    Location,
    RequestScope,
)


def make_catalog(**overrides):
    defaults = dict(
        default_location="/srv/focus/default",
        default_version="1.0",
        datasets={},
        allow_raw_locations=False,
    )
    defaults.update(overrides)
    return Catalog(**defaults)


def test_no_handle_means_the_process_default():
    assert make_catalog().resolve() == Dataset.at("/srv/focus/default", "1.0")


def test_version_override_applies_to_the_default_and_drops_the_v_prefix():
    assert make_catalog().resolve(version="v1.2").version == "1.2"


def test_static_datasets_resolve_by_name_with_their_own_version():
    catalog = make_catalog(datasets={"prod": {"location": "s3://lake/focus/prod", "version": "1.2"}})
    assert catalog.resolve("prod") == Dataset.at("s3://lake/focus/prod", "1.2", "prod")
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


def scope_of(**headers):
    return RequestScope.from_headers(headers, "1.0")


def test_request_datasets_come_from_the_header_in_order():
    scope = scope_of(**{"X-Focus-Datasets": "all=s3://lake/focus/t-5/, proxy=s3://lake/focus/t-5/proxy/@1.1"})
    assert list(scope.datasets) == ["all", "proxy"]
    assert scope.default == "all"
    assert scope.datasets["all"] == Dataset.at("s3://lake/focus/t-5/", "1.0", "all")
    assert scope.datasets["proxy"].version == "1.1"


def test_request_version_applies_to_every_dataset_without_its_own():
    scope = scope_of(**{"x-focus-datasets": "a=s3://x/, b=s3://y/@1.0", "x-focus-version": "v1.2"})
    assert scope.datasets["a"].version == "1.2"
    assert scope.datasets["b"].version == "1.0"


def test_request_datasets_replace_the_process_defaults():
    catalog = make_catalog(datasets={"host": {"location": "/data/host", "version": ""}})
    scope = scope_of(**{"x-focus-datasets": "mine=s3://lake/focus/t-5/"})
    assert catalog.resolve(scope=scope).handle == "mine"
    assert catalog.resolve("mine", "1.2", scope=scope).version == "1.2"
    with pytest.raises(DatasetError, match="This request may read: mine"):
        catalog.resolve("host", scope=scope)


def test_a_request_without_datasets_falls_back_to_the_process():
    catalog = make_catalog(datasets={"host": {"location": "/data/host", "version": ""}})
    assert catalog.resolve("host", scope=scope_of()).location == "/data/host"
    assert catalog.resolve(scope=scope_of(**{"x-aws-region": "eu-west-1"})).location == "/srv/focus/default"


@pytest.mark.parametrize("header", ["all", "All=s3://x/", "a=nowhere", "a=s3://x/,=s3://y/"])
def test_malformed_dataset_headers_are_refused(header):
    with pytest.raises(DatasetError):
        scope_of(**{"x-focus-datasets": header})


def test_credentials_are_read_from_headers_and_never_printed():
    scope = scope_of(**{
        "X-Aws-Access-Key-Id": "AKIAEXAMPLE",
        "X-Aws-Secret-Access-Key": "hunter2",
        "X-Aws-Session-Token": "tok",
        "X-Aws-Region": "eu-west-1",
    })
    assert scope.credentials == Credentials("AKIAEXAMPLE", "hunter2", "tok", "eu-west-1")
    assert "hunter2" not in repr(scope.credentials)
    assert scope_of().credentials is None


def test_half_a_credential_is_an_error():
    with pytest.raises(DatasetError, match="both"):
        scope_of(**{"x-aws-access-key-id": "AKIA"})


def test_a_location_may_carry_its_own_region():
    scope = scope_of(**{"x-focus-datasets": (
        "lake=s3://billing-lake/focus/@eu-west-1, plain=s3://billing-lake/other/"
    )})
    assert scope.datasets["lake"].locations == (Location("s3://billing-lake/focus/", "eu-west-1"),)
    # No region of its own: X-Aws-Region, the session default, applies
    assert scope.datasets["plain"].locations == (Location("s3://billing-lake/other/", ""),)


def test_a_numeric_suffix_is_a_version_not_a_region():
    scope = scope_of(**{"x-focus-datasets": "archive=s3://billing-lake/focus-2025/@1.0"})
    assert scope.datasets["archive"].version == "1.0"
    assert scope.datasets["archive"].locations[0].region == ""


def test_a_repeated_handle_is_one_dataset_of_several_locations():
    scope = scope_of(**{"x-focus-datasets": (
        "aws-123456789012=s3://billing-lake/converted/@eu-west-1, "
        "aws-123456789012=s3://customer-exports/focus/data/@us-east-1"
    )})
    assert list(scope.datasets) == ["aws-123456789012"]
    assert scope.datasets["aws-123456789012"].locations == (
        Location("s3://billing-lake/converted/", "eu-west-1"),
        Location("s3://customer-exports/focus/data/", "us-east-1"),
    )


def test_the_first_entry_of_a_repeated_handle_sets_the_version():
    scope = scope_of(**{"x-focus-datasets": "a=s3://one/@1.2, a=s3://two/"})
    assert scope.datasets["a"].version == "1.2"
    assert len(scope.datasets["a"].locations) == 2


def test_resolving_a_repeated_handle_keeps_every_location():
    scope = scope_of(**{"x-focus-datasets": "a=s3://one/, a=s3://two/"})
    resolved = make_catalog().resolve("a", scope=scope)
    assert resolved.locations == (Location("s3://one/"), Location("s3://two/"))
    # The first location is what names the dataset in messages
    assert resolved.location == "s3://one/"
