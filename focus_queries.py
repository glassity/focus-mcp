#!/usr/bin/env python3
"""FOCUS Query Library - loads SQL queries from directory based on config version."""

from pathlib import Path
from dataclasses import dataclass
import focus_config


@dataclass
class Query:
    name: str
    description: str
    query: str
    citation: str = ""
    filename: str = ""


class QueryLoader:
    def __init__(self):
        self.queries: dict[str, Query] = {}
        self._load_queries()

    def _load_queries(self):
        base_dir = Path("resources/queries")
        version_dir = f"queries_v{focus_config.FOCUS_VERSION.replace('.', '_')}"
        queries_dir = base_dir / version_dir

        if not queries_dir.exists():
            print(f"Warning: Queries directory {queries_dir} does not exist")
            return

        for sql_file in queries_dir.glob("*.sql"):
            if query := self._parse_file(sql_file):
                self.queries[sql_file.stem] = query

    def _parse_file(self, filepath: Path) -> Query | None:
        try:
            content = filepath.read_text()
            lines = content.split("\n")

            name = lines[0].replace("-- ", "") if lines else filepath.stem
            source = ""
            for line in lines:
                if "Source:" in line:
                    source = line.replace("-- Source: ", "").strip()
                    break

            sql_lines = [line for line in lines if not line.startswith("--")]
            sql = "\n".join(sql_lines).strip()

            if not sql:
                return None

            return Query(
                name=name,
                description="Query from focus.finops.org",
                query=sql,
                citation=source,
                filename=filepath.name,
            )

        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None

    def get_query(self, query_name: str) -> Query | None:
        return self.queries.get(query_name)


focus_queries = QueryLoader()
