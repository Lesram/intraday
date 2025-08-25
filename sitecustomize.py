import os, sys, types
os.environ.setdefault("DISABLE_ML", "1")
HEAVY = ("torch","transformers","tensorflow","xgboost","lightgbm","spacy","pytorch_lightning")
def _stub_tf():
    tf = types.ModuleType("tensorflow")
    tf.keras = types.SimpleNamespace(models=types.SimpleNamespace(Sequential=object))
    return tf
def _stub(name):
    if name == "tensorflow": return _stub_tf()
    m = types.ModuleType(name)
    if name == "transformers":
        def _blocked(*a, **k): raise RuntimeError("transformers disabled")
        m.pipeline = _blocked
    return m
if os.environ.get("DISABLE_ML") == "1":
    for p in HEAVY:
        if p not in sys.modules: sys.modules[p] = _stub(p)