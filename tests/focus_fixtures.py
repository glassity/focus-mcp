"""Synthetic FOCUS data, one table per specification version.

No public dataset exists for FOCUS 1.1 or later, so query execution is
tested against generated rows instead. The schema comes from
resources/specifications/columns.yaml filtered by introduced_version, so a
version gets exactly the columns the spec says it has - and a query that
reaches for a column from a later version fails here rather than in
production.

Values are seeded so queries return rows: timestamps sit inside the window
tests/query_params.yaml uses, and list prices exceed effective ones so
savings filters keep the row rather than trivially matching nothing.
"""

import json

import duckdb
import yaml
from focus_mcp.paths import resource_path
from focus_mcp.spec_loader import _available_at

SQL_TYPES = {
    "String": "VARCHAR",
    "Decimal": "DOUBLE",
    "Date/Time": "TIMESTAMP WITH TIME ZONE",
    "JSON": "VARCHAR",
}

# Inside the 2025-05-01..2025-09-30 window query_params.yaml filters on.
TIMESTAMP = "TIMESTAMP '2025-06-15 00:00:00+00'"
LATER = "TIMESTAMP '2025-07-15 00:00:00+00'"

# One row cannot satisfy filters that exclude each other - a charge is
# either a credit or usage, a commitment is either used or unused - so the
# fixture carries a row per case the queries discriminate on. Each entry
# overrides the baseline row; a value of None means SQL NULL.
ROW_VARIANTS = [
    {},                                                     # standard usage
    {"ChargeCategory": "Credit", "BilledCost": -5.0, "EffectiveCost": -5.0},
    {"ChargeCategory": "Purchase", "ChargeFrequency": "One-Time"},
    {"ChargeCategory": "Tax"},
    {"ChargeClass": "Correction"},                          # a correction
    {"CommitmentDiscountStatus": "Unused", "ConsumedQuantity": None},
    {"CapacityReservationStatus": "Unused"},
    {"CommitmentDiscountStatus": None, "CommitmentDiscountId": None,
     "PricingCategory": "On-Demand"},                       # uncommitted spend
    {"PublisherName": "Acme Software", "ServiceProviderName": "Acme Software",
     "InvoiceIssuerName": "AWS Marketplace"},               # marketplace resale
    {"PricingCurrency": "EUR", "PricingCurrencyEffectiveCost": 9.0,
     "PricingCurrencyListUnitPrice": 18.0,
     "PricingCurrencyContractedUnitPrice": 11.0},           # virtual currency
    {"ServiceName": "Amazon Simple Storage Service",
     "ServiceCategory": "Storage", "ServiceSubcategory": "Object Storage",
     "RegionId": "us-east-1", "RegionName": "US East (N. Virginia)",
     "AvailabilityZone": "us-east-1a"},                     # a second service
    {"_period": "2025-07", "_timestamp": LATER},            # a second period
    {"_period": "2025-07", "_timestamp": LATER,
     "ChargeClass": "Correction"},                          # correction, later
]

# Values that keep rows past the WHERE clauses the queries actually use.
STRINGS = {
    "ChargeCategory": "Usage",
    "ChargeClass": "",
    "ChargeFrequency": "Usage-Based",
    "CommitmentDiscountStatus": "Used",
    "CommitmentDiscountCategory": "Usage",
    "CommitmentDiscountType": "Reserved Instance",
    "PricingCategory": "Standard",
    "BillingCurrency": "USD",
    "PricingCurrency": "USD",
    "ServiceCategory": "Compute",
    "ServiceSubcategory": "Virtual Machines",
    "ServiceName": "Amazon Elastic Compute Cloud",
    "ProviderName": "AWS",
    "PublisherName": "AWS",
    # 1.3 replaced ProviderName; without these the newest collections would
    # filter on "test-ServiceProviderName" and match nothing.
    "ServiceProviderName": "AWS",
    "HostProviderName": "AWS",
    "InvoiceIssuerName": "AWS",
    "BillingAccountId": "111111111111",
    "BillingAccountName": "Test Billing Account",
    "SubAccountId": "222222222222",
    "SubAccountName": "Test Sub Account",
    "RegionId": "eu-west-1",
    "RegionName": "EU (Ireland)",
    "AvailabilityZone": "eu-west-1a",
    "ResourceId": "i-0123456789abcdef0",
    "ResourceName": "test-instance",
    "ResourceType": "Instance",
    "SkuId": "SKU-1",
    "SkuPriceId": "SKUPRICE-1",
    "PricingUnit": "Hours",
    "ConsumedUnit": "Hours",
    "CapacityReservationId": "cr-01234567",
    "CapacityReservationStatus": "Used",
    "CommitmentDiscountId": "cd-01234567",
    "CommitmentDiscountName": "Test Commitment",
    "CommitmentDiscountUnit": "Hours",
    "CommitmentDiscountQuantity": "1",
    "InvoiceId": "INV-0001",
    "ChargeDescription": "Test charge",
    "ChargePeriodStart": None,  # typed Date/Time; listed for readability
}

# Decimals default to 10.0; list prices are higher so contracted savings and
# discount queries see a positive delta.
DECIMALS = {
    "ListCost": 20.0,
    "ListUnitPrice": 20.0,
    "PricingCurrencyListUnitPrice": 20.0,
    "PricingCurrencyListCost": 20.0,
    "ContractedCost": 12.0,
    "ContractedUnitPrice": 12.0,
    "PricingCurrencyContractedUnitPrice": 12.0,
}

# Tag keys the queries look for by name.
TAGS = {
    "Application": "web",
    "ApplicationId": "app-1",
    "Environment": "prod",
    "Team": "platform",
    "CostCenter": "cc-1",
}
SKU_PRICE_DETAILS = {
    "CoreCount": "8",
    "InstanceSeries": "m5",
    "x_MeteredQuantity": "1",
}

# 1.3+ object columns hold arrays the queries UNNEST, so a flat key/value
# payload would leave every one of them matching nothing.
NESTED_JSON = {
    "ContractApplied": {
        "Elements": [
            {"ContractCommitmentID": "cc-0001",
             # a JSON number, not a string: the queries cast it to a numeric
             "ContractCommitmentAppliedCost": 5.0,
             "ContractCommitmentCategory": "Spend"}
        ]
    },
    "CommitmentProgramEligibilityDetails": {
        "CommitmentPrograms": [
            {"ProgramType": "Reserved Instance", "Eligible": "true"}
        ]
    },
    "AllocatedMethodDetails": {"AllocatedMethodID": "am-0001"},
}


def columns_for(version: str) -> list[dict]:
    """The spec's columns as of a version, oldest first.

    A column is present once introduced and until retired: the spec deletes
    a retired column's file rather than marking it, so a version that still
    has ProviderName must not be given 1.4's column list.
    """
    with open(resource_path("specifications", "columns.yaml"), encoding="utf-8") as f:
        columns = yaml.safe_load(f)

    # The production predicate, not a copy: a fixture that disagreed with
    # the server would agree with itself and prove nothing.
    return [c for c in columns if _available_at(c, version)]


def _json_payload(name: str) -> dict:
    if name in NESTED_JSON:
        return NESTED_JSON[name]
    return SKU_PRICE_DETAILS if name == "SkuPriceDetails" else TAGS


def _sql_type(column: dict, json_shape: str) -> str:
    kind = column.get("data_type", "String")
    # Only the flat key/value columns are delivered as MAP; the nested
    # object columns have no MAP equivalent and stay JSON text.
    if (kind == "JSON" and json_shape == "map"
            and column["column_id"] not in NESTED_JSON):
        return "MAP(VARCHAR, VARCHAR)"
    return SQL_TYPES.get(kind, "VARCHAR")


def _value(column: dict, json_shape: str) -> str:
    name, kind = column["column_id"], column.get("data_type", "String")
    if kind == "Date/Time":
        return TIMESTAMP
    if kind == "Decimal":
        return str(DECIMALS.get(name, 10.0))
    if kind == "JSON":
        payload = _json_payload(name)
        if json_shape == "map" and name not in NESTED_JSON:
            pairs = ", ".join(f"'{k}': '{v}'" for k, v in payload.items())
            return f"MAP{{{pairs}}}"
        return _quote(json.dumps(payload))
    return _quote(STRINGS[name] if name in STRINGS else f"test-{name}")


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _override(column: dict, value, json_shape: str) -> str:
    kind = column.get("data_type", "String")
    if value is None:
        return "NULL"
    if kind == "Decimal":
        return str(value)
    if kind == "Date/Time":
        return value
    return _quote(str(value))


def _row(columns, variant, json_shape) -> str:
    timestamp = variant.get("_timestamp", TIMESTAMP)
    cells = []
    for column in columns:
        name = column["column_id"]
        if name in variant:
            cells.append(_override(column, variant[name], json_shape))
        elif column.get("data_type") == "Date/Time":
            cells.append(timestamp)
        else:
            cells.append(_value(column, json_shape))
    cells.append(_quote(variant.get("_period", "2025-06")))
    return "(" + ", ".join(cells) + ")"


def build_table(
    conn: duckdb.DuckDBPyConnection, version: str, json_shape: str = "json"
) -> list[str]:
    """Create focus_data_table for a FOCUS version.

    json_shape selects how the spec's JSON columns are physically typed:
    "json" is the VARCHAR the specification describes, "map" is what AWS
    Data Exports actually deliver. Queries have to work against both, and
    only executing them proves it.
    """
    columns = columns_for(version)
    names = {c["column_id"] for c in columns}
    declarations = ", ".join(
        f'"{c["column_id"]}" {_sql_type(c, json_shape)}' for c in columns
    )
    rows = ", ".join(
        _row(columns, {k: v for k, v in variant.items()
                       if k.startswith("_") or k in names}, json_shape)
        for variant in ROW_VARIANTS
    )

    conn.execute("INSTALL json; LOAD json;")
    conn.execute(
        f'CREATE TABLE focus_data_table ({declarations}, "billing_period" VARCHAR)'
    )
    conn.execute(f"INSERT INTO focus_data_table VALUES {rows}")
    return [c["column_id"] for c in columns]
