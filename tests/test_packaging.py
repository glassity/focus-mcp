"""Resources must resolve from the installed package, not the working directory.

These are regression tests for two real defects: FocusSpecLoader defaulted to
the CWD-relative path "resources/specifications", and queries.py resolved
resources via Path(__file__).parent, which only worked because the wheel
dumped resources/ next to the module at site-packages root.
"""

from focus_mcp.paths import resource_path
from focus_mcp.spec_loader import FocusSpecLoader


def test_resource_path_is_absolute_and_exists():
    path = resource_path("specifications", "columns.yaml")
    assert path.is_absolute()
    assert path.exists()


def test_spec_loader_finds_resources_from_any_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    loader = FocusSpecLoader()
    assert len(loader.columns) > 0
    assert len(loader.attributes) > 0


def test_spec_loader_honours_an_explicit_directory(tmp_path):
    """Covers the explicit-directory contract that scripts/ extractors and other
    tests rely on, not the resource-resolution defect: Path(spec_dir) behaves
    identically before and after the fix whenever spec_dir is not None.
    """
    loader = FocusSpecLoader(spec_dir=str(tmp_path))
    assert loader.columns == []
    assert loader.attributes == []


def test_queries_do_not_depend_on_module_file_location(monkeypatch, tmp_path):
    """queries.py used to resolve resources via Path(__file__).parent, which only
    worked because the old wheel dumped resources/ beside the module. Resolution
    must come from the package, not from this module's location on disk, so we
    break __file__ deliberately: the old code would fail to find the YAML files,
    the new code (importlib.resources, keyed off the package spec) is unaffected.
    """
    monkeypatch.chdir(tmp_path)
    import focus_mcp.queries as queries_module

    monkeypatch.setattr(
        queries_module, "__file__", str(tmp_path / "not-the-package" / "queries.py")
    )
    loader = queries_module.QueryLoader()
    assert len(loader.queries) > 0
