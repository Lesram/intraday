"""Test factory import"""
try:
    print("Importing create_app...")
    from backend.api.factory import create_app
    print("create_app imported successfully")
    
    print("Calling create_app...")
    app = create_app()
    print("App created")
    print(f"App type: {type(app)}")
    print(f"App has lifespan: {hasattr(app, 'router')}")
    
    # Check lifespan_context
    print(f"App lifespan_context: {getattr(app, 'lifespan_context', 'NOT FOUND')}")
    
except Exception as e:
    print(f"Error importing or using create_app: {e}")
    import traceback
    print(traceback.format_exc())
