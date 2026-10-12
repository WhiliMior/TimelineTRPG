def test_plugin_package_imports():
    from timeline_trpg import main

    plugin = main.TimelineTRPG(context=None)
    assert "r" in plugin.router.list_commands()


def test_version_matches_metadata():
    import re
    from pathlib import Path

    from timeline_trpg import main

    metadata = (Path(__file__).parent.parent / "metadata.yaml").read_text("utf-8")
    version = re.search(r"^version:\s*(\S+)", metadata, re.M).group(1)
    assert main.PLUGIN_VERSION == version
