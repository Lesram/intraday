def test_api_main_import_smoke():
	from backend.api import main
	assert hasattr(main, "app")
