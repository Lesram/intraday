import importlib

def test_broker_service_patch_path_importable():
    m = importlib.import_module('backend.services.broker_service')
    assert m is not None
