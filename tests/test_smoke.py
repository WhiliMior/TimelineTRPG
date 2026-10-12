def test_plugin_package_imports():
    from timeline_trpg import main

    plugin = main.TimelineTRPG(context=None)
    assert "r" in plugin.router.list_commands()
