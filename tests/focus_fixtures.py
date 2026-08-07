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
from packaging.version import parse

from focus_mcp.paths import resource_path

SQL_TYPES = {
    "String": "VARCHAR",
    "Decimal": "DOUBLE",
    "Date/Time": "TIMESTAMP WITH TIME ZONE",
    "JSON": "VARCHAR",
}

# Inside the 2025-05-01..2025-09-30 window query_params.yaml filters on.
TIMESTAMP = "TIMESTAMP '2025-06-15 00:00:00+00'"

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


def columns_for(version: str) -> list[dict]:
    """The spec's columns as of a version, oldest first."""
    with open(resource_path("specifications", "columns.yaml"), encoding="utf-8") as f:
        columns = yaml.safe_load(f)

    def introduced(column):
        return parse(column.get("introduced_version", "0").replace("-preview", "a0"))

    target = parse(version.replace("-preview", "a0"))
    return [c for c in columns if introduced(c) <= target]


def _json_payload(name: str) -> dict[str, str]:
    return SKU_PRICE_DETAILS if name == "SkuPriceDetails" else TAGS


def _sql_type(column: dict, json_shape: str) -> str:
    kind = column.get("data_type", "String")
    if kind == "JSON" and json_shape == "map":
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
        if json_shape == "map":
            pairs = ", ".join(f"'{k}': '{v}'" for k, v in payload.items())
            return f"MAP{{{pairs}}}"
        return _quote(json.dumps(payload))
    return _quote(STRINGS.get(name) or f"test-{name}")


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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
    declarations = ", ".join(
        f'"{c["column_id"]}" {_sql_type(c, json_shape)}' for c in columns
    )
    values = ", ".join(_value(c, json_shape) for c in columns)

    conn.execute("INSTALL json; LOAD json;")
    conn.execute(
        f'CREATE TABLE focus_data_table ({declarations}, "billing_period" VARCHAR)'
    )
    conn.execute(f"INSERT INTO focus_data_table VALUES ({values}, '2025-06')")
    return [c["column_id"] for c in columns]
