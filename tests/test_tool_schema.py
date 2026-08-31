"""The dataset and version parameters are advertised as header-mirrored.

MCP 2026-07-28 lets a tool mark parameters with x-mcp-header so Streamable
HTTP clients mirror them into Mcp-Param-* headers; gateways can then route
and meter by dataset without parsing the body. Every data tool must carry
the same two annotations, or a gateway rule written for one tool silently
misses another.
"""

import asyncio

from focus_mcp import server


def tools_by_name():
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def header_of(tool, param):
    return tool.input_schema["properties"][param].get("x-mcp-header")


def test_data_tools_take_a_dataset_handle():
    tools = tools_by_name()
    for name in ("get_data_info", "execute_query"):
        assert header_of(tools[name], "dataset") == "Dataset", name
        assert header_of(tools[name], "focus_version") == "Focus-Version", name


def test_query_library_tools_take_a_version():
    tools = tools_by_name()
    for name in ("list_use_cases", "get_use_case"):
        assert header_of(tools[name], "focus_version") == "Focus-Version", name


def test_spec_tools_keep_their_version_parameter_and_mirror_it():
    tools = tools_by_name()
    for name in ("list_columns", "get_column_details", "list_attributes", "get_attribute_details"):
        assert header_of(tools[name], "version") == "Focus-Version", name


def test_header_names_are_unique_within_each_tool():
    for tool in tools_by_name().values():
        names = [
            p["x-mcp-header"].lower()
            for p in tool.input_schema["properties"].values()
            if "x-mcp-header" in p
        ]
        assert len(names) == len(set(names)), tool.name


def test_wire_format_carries_the_annotation():
    tool = tools_by_name()["execute_query"]
    wire = tool.model_dump(by_alias=True, mode="json")
    assert wire["inputSchema"]["properties"]["dataset"]["x-mcp-header"] == "Dataset"


def test_header_annotated_parameters_are_plain_strings():
    # An Optional[str] renders as anyOf without a type keyword, and the
    # client then drops the whole tool as having an invalid annotation.
    for tool in tools_by_name().values():
        for name, prop in tool.input_schema["properties"].items():
            if "x-mcp-header" in prop:
                assert prop.get("type") == "string", (tool.name, name, prop)
