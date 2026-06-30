"""Public-API surface contract test.

Guards the import / entry-point contract documented in
``docs/internal/CONTRACTS/PUBLIC_API.md``. If this test needs to change, the public API is
changing — update the contract doc and ``CHANGELOG.md`` in the same change.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from importlib.resources import files

# Declared in pyproject.toml [project.scripts]; renaming/removing any of these is
# a breaking change requiring a deprecation cycle + CHANGELOG entry.
EXPECTED_CONSOLE_SCRIPTS = {
    "hydramem": "hydramem.cli:main",
    "hydramem-server": "hydramem.server:main",
    "hydramem-dashboard": "hydramem.dashboard:main",
}


def test_package_imports() -> None:
    import hydramem  # noqa: F401


def test_cli_entry_point_callable() -> None:
    from hydramem.cli import main

    assert callable(main)


def test_console_scripts_declared() -> None:
    eps = importlib_metadata.entry_points(group="console_scripts")
    found = {ep.name: ep.value for ep in eps if ep.name in EXPECTED_CONSOLE_SCRIPTS}
    assert found == EXPECTED_CONSOLE_SCRIPTS


def test_py_typed_marker_ships() -> None:
    marker = files("hydramem").joinpath("py.typed")
    assert marker.is_file(), "PEP 561 py.typed marker must ship with the package"
