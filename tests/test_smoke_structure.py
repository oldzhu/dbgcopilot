def test_structure_exists():
    # Basic smoke test to ensure key modules exist
    import importlib

    assert importlib.import_module("dbgcopilot")
    assert importlib.import_module("dbgcopilot.core.orchestrator")
    assert importlib.import_module("dbgcopilot.backends.gdb_inprocess")
    assert importlib.import_module("dbgcopilot.backends.python_pdb")
    assert importlib.import_module("dbgcopilot.backends.lldb_rust")
    assert importlib.import_module("dbgcopilot.backends.lldb_rust_api")
    assert importlib.import_module("dbgcopilot.backends.java_jdb")
    assert importlib.import_module("dbgcopilot.backends.rust_gdb")
