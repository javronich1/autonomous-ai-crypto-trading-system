"""Smoke tests for the top-level package."""


def test_package_imports() -> None:
    """The repository's top-level package is importable."""
    import crypto_trader

    assert crypto_trader.__version__ == "0.0.1"
