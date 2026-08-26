import adhoc


def test_version_matches_pyproject():
    assert adhoc.__version__ == "0.0.1"


def test_public_surface_is_importable():
    import adhoc.__main__

    assert callable(adhoc.__main__.main)
