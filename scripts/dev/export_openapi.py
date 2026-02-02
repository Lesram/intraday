#!/usr/bin/env python3
"""
OpenAPI Schema Export Script

This script exports the OpenAPI schema from the FastAPI application
to a JSON file for documentation, contract validation, and external integrations.

Usage:
    python scripts/export_openapi.py [--output OUTPUT_FILE] [--format FORMAT]

Examples:
    python scripts/export_openapi.py
    python scripts/export_openapi.py --output api_schema.json
    python scripts/export_openapi.py --output api_schema.yaml --format yaml
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from backend.api.main import create_app
except ImportError as e:
    print(f"Error importing FastAPI app: {e}")
    print("Make sure you're running this script from the project root directory")
    sys.exit(1)


def export_openapi_schema(output_file: str = "openapi.json", format_type: str = "json") -> Dict[str, Any]:
    """
    Export OpenAPI schema from FastAPI application.
    
    Args:
        output_file: Output file path
        format_type: Output format ('json' or 'yaml')
        
    Returns:
        The OpenAPI schema dictionary
        
    Raises:
        Exception: If schema export fails
    """
    try:
        # Create FastAPI app instance
        app = create_app()
        
        # Get OpenAPI schema
        openapi_schema = app.openapi()
        
        # Validate schema has required fields
        if not openapi_schema.get("openapi"):
            raise ValueError("Invalid OpenAPI schema: missing 'openapi' version")
            
        if not openapi_schema.get("info"):
            raise ValueError("Invalid OpenAPI schema: missing 'info' section")
            
        # Write to file
        output_path = Path(output_file)
        
        if format_type.lower() == "yaml":
            try:
                import yaml
                with output_path.open("w", encoding="utf-8") as f:
                    yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)
            except ImportError:
                print("Warning: PyYAML not installed, falling back to JSON format")
                format_type = "json"
        
        if format_type.lower() == "json":
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
        
        # Print summary
        info = openapi_schema.get("info", {})
        paths_count = len(openapi_schema.get("paths", {}))
        components_count = len(openapi_schema.get("components", {}).get("schemas", {}))
        
        print(f"✅ OpenAPI schema exported successfully!")
        print(f"   📄 File: {output_path.absolute()}")
        print(f"   📊 Format: {format_type.upper()}")
        print(f"   🔢 API Version: {info.get('version', 'unknown')}")
        print(f"   📝 Title: {info.get('title', 'unknown')}")
        print(f"   🛣️  Paths: {paths_count}")
        print(f"   📋 Schemas: {components_count}")
        
        # Check for security schemes
        security_schemes = openapi_schema.get("components", {}).get("securitySchemes", {})
        if security_schemes:
            print(f"   🔒 Security Schemes: {', '.join(security_schemes.keys())}")
        
        return openapi_schema
        
    except Exception as e:
        print(f"❌ Error exporting OpenAPI schema: {e}")
        raise


def main():
    """Main entry point for the export script."""
    parser = argparse.ArgumentParser(
        description="Export OpenAPI schema from FastAPI application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Export to openapi.json
  %(prog)s --output docs/api_schema.json      # Custom output file
  %(prog)s --output schema.yaml --format yaml # Export as YAML
        """
    )
    
    parser.add_argument(
        "--output", "-o",
        default="openapi.json",
        help="Output file path (default: openapi.json)"
    )
    
    parser.add_argument(
        "--format", "-f",
        choices=["json", "yaml"],
        default="json",
        help="Output format: json or yaml (default: json)"
    )
    
    parser.add_argument(
        "--validate", "-v",
        action="store_true",
        help="Validate schema without writing to file"
    )
    
    args = parser.parse_args()
    
    try:
        if args.validate:
            # Validation mode - just check schema is valid
            app = create_app()
            schema = app.openapi()
            print("✅ OpenAPI schema validation passed")
            print(f"   API: {schema.get('info', {}).get('title', 'Unknown')} v{schema.get('info', {}).get('version', 'unknown')}")
            print(f"   Paths: {len(schema.get('paths', {}))}")
        else:
            # Export mode
            export_openapi_schema(args.output, args.format)
            
    except Exception as e:
        print(f"❌ Export failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()