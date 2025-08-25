import os, sys, types
os.environ.setdefault("DISABLE_ML","1")
if os.environ["DISABLE_ML"]=="1":
    for n in ("torch","transformers","tensorflow","xgboost","lightgbm","spacy","pytorch_lightning"):
        if n not in sys.modules:
            sys.modules[n]=types.ModuleType(n)
