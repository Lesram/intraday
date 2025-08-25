import sys, os
print("LightMode:", os.environ.get("DISABLE_ML"))
print("torch stubbed:", "torch" in sys.modules)
print("httpx stubbed:", "httpx" in sys.modules)
print("prometheus_client stubbed:", "prometheus_client" in sys.modules)
