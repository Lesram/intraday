import importlib, sys
try:
    m = importlib.import_module("backend.config.settings")
    print("OK:", hasattr(m, "settings"))
    print("Module file:", getattr(m, "__file__", None))
except Exception as e:
    print("ERROR:", type(e).__name__, str(e))
    import traceback; traceback.print_exc()
    sys.exit(1)
