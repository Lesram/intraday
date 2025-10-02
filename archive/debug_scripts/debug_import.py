#!/usr/bin/env python3
try:
    import backend.database
    print("Import successful")
    print("Module file:", backend.database.__file__)
    
    config = backend.database.DatabaseConfig()
    print("DatabaseConfig created:", type(config))
    print("Has url attribute:", hasattr(config, 'url'))
    
    if hasattr(config, 'url'):
        print("URL value:", config.url)
    else:
        print("Available attributes:", [attr for attr in dir(config) if not attr.startswith('_')])
        
    # Check if it's really a dataclass
    import dataclasses
    print("Is dataclass:", dataclasses.is_dataclass(config))
    
except Exception as e:
    print("Import error:", e)
    import traceback
    traceback.print_exc()