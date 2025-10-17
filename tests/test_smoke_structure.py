def test_structure_exists():
    # Basic smoke test to ensure key modules exist
    import importlib

    assert importlib.import_module("dbgcopilot")
    assert importlib.import_module("dbgcopilot.core.orchestrator")
    assert importlib.import_module("dbgcopilot.backends.gdb_inprocess")
