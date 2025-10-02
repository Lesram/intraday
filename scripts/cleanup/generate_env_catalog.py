#!/usr/bin/env python3
"""
Environment Variable Catalog Generator
Extracts all environment variables from code, config, and infrastructure.
"""

import ast
import json
import os
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Optional
from collections import defaultdict


@dataclass
class EnvVar:
    """Environment variable metadata."""
    name: str
    classification: str  # secret, config, derived
    default_value: Optional[str]
    required: bool
    usage_locations: List[str]
    found_in_envs: List[str]  # dev, paper, staging, production
    description: Optional[str] = None


class EnvCatalogGenerator:
    """Extract and catalog all environment variables."""
    
    def __init__(self, root_dir: Path):
        self.root = root_dir
        self.env_vars: Dict[str, EnvVar] = {}
        
        # Secret patterns
        self.secret_patterns = re.compile(
            r'(SECRET|KEY|TOKEN|PASSWORD|CREDENTIAL|AUTH|PRIVATE)',
            re.IGNORECASE
        )
        
        # Environment files to scan
        self.env_files = [
            '.env',
            '.env.paper',
            '.env.production',
            '.env.staging',
            '.env.production.template'
        ]
        
    def extract_from_python(self) -> Set[str]:
        """Extract env vars from Python code."""
        print("🐍 Scanning Python files for environment variables...")
        
        env_vars = defaultdict(list)
        patterns = [
            re.compile(r'os\.getenv\([\'"]([A-Z_][A-Z0-9_]*)[\'"]'),
            re.compile(r'os\.environ\.get\([\'"]([A-Z_][A-Z0-9_]*)[\'"]'),
            re.compile(r'os\.environ\[[\'"]([A-Z_][A-Z0-9_]*)[\'"]'),
            re.compile(r'env\([\'"]([A-Z_][A-Z0-9_]*)[\'"]'),
        ]
        
        for py_file in self.root.rglob('*.py'):
            if '.venv' in str(py_file) or 'venv' in str(py_file):
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                rel_path = str(py_file.relative_to(self.root))
                
                for pattern in patterns:
                    for match in pattern.finditer(content):
                        var_name = match.group(1)
                        env_vars[var_name].append(rel_path)
                
            except (UnicodeDecodeError, PermissionError):
                pass
        
        print(f"✅ Found {len(env_vars)} environment variables in Python code")
        return env_vars
    
    def extract_from_pydantic(self) -> Dict[str, tuple]:
        """Extract from Pydantic BaseSettings classes."""
        print("⚙️  Scanning Pydantic settings classes...")
        
        settings_vars = {}
        
        # Look for settings files
        settings_files = [
            self.root / 'backend' / 'config' / 'base_settings.py',
            self.root / 'backend' / 'config' / 'settings.py',
            self.root / 'backend' / 'settings.py',
        ]
        
        for settings_file in settings_files:
            if not settings_file.exists():
                continue
            
            try:
                content = settings_file.read_text(encoding='utf-8')
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Check if it's a Settings class
                        if any('Settings' in base.id for base in node.bases if isinstance(base, ast.Name)):
                            for item in node.body:
                                if isinstance(item, ast.AnnAssign):
                                    if isinstance(item.target, ast.Name):
                                        var_name = item.target.id.upper()
                                        default = None
                                        if item.value:
                                            try:
                                                default = ast.literal_eval(item.value)
                                            except:
                                                pass
                                        settings_vars[var_name] = (default, str(settings_file.relative_to(self.root)))
                
            except (SyntaxError, UnicodeDecodeError):
                pass
        
        print(f"✅ Found {len(settings_vars)} variables in Pydantic settings")
        return settings_vars
    
    def parse_env_file(self, env_file_path: Path) -> Dict[str, str]:
        """Parse a .env file."""
        if not env_file_path.exists():
            return {}
        
        vars_dict = {}
        try:
            content = env_file_path.read_text(encoding='utf-8')
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    vars_dict[key] = value
        
        except (UnicodeDecodeError, PermissionError):
            pass
        
        return vars_dict
    
    def scan_env_files(self) -> Dict[str, Dict[str, str]]:
        """Scan all .env files."""
        print("📄 Scanning .env files...")
        
        env_data = {}
        for env_file in self.env_files:
            env_path = self.root / env_file
            vars_dict = self.parse_env_file(env_path)
            if vars_dict:
                env_data[env_file] = vars_dict
                print(f"  ✅ {env_file}: {len(vars_dict)} variables")
        
        return env_data
    
    def classify_var(self, var_name: str, value: Optional[str]) -> str:
        """Classify an environment variable."""
        if self.secret_patterns.search(var_name):
            return 'secret'
        
        # Check value patterns
        if value:
            if any(pattern in value.lower() for pattern in ['pk', 'sk', 'key_', 'bearer', 'Basic']):
                return 'secret'
            if value.startswith('__') or value == '__set_in_secret_store__':
                return 'secret'
        
        # Configuration variables
        config_patterns = ['URL', 'HOST', 'PORT', 'PATH', 'DIR', 'LEVEL', 'MODE', 'ENABLE', 'DISABLE', 'MAX', 'MIN']
        if any(pattern in var_name for pattern in config_patterns):
            return 'config'
        
        return 'config'
    
    def generate_catalog(self) -> Dict[str, EnvVar]:
        """Generate comprehensive environment variable catalog."""
        print("\n🔍 Generating environment variable catalog...\n")
        
        # Extract from all sources
        python_vars = self.extract_from_python()
        pydantic_vars = self.extract_from_pydantic()
        env_file_data = self.scan_env_files()
        
        # Combine all sources
        all_var_names = set(python_vars.keys()) | set(pydantic_vars.keys())
        for env_file, vars_dict in env_file_data.items():
            all_var_names.update(vars_dict.keys())
        
        # Build catalog
        for var_name in sorted(all_var_names):
            usage_locations = python_vars.get(var_name, [])
            default_value = None
            
            if var_name in pydantic_vars:
                default_value, loc = pydantic_vars[var_name]
                if loc not in usage_locations:
                    usage_locations.append(loc)
            
            # Check which env files contain this var
            found_in_envs = []
            for env_file, vars_dict in env_file_data.items():
                if var_name in vars_dict:
                    found_in_envs.append(env_file)
                    if not default_value:
                        default_value = vars_dict[var_name]
            
            classification = self.classify_var(var_name, default_value)
            
            # Determine if required (no default and used in code)
            required = (default_value is None or default_value == '__set_in_secret_store__') and len(usage_locations) > 0
            
            self.env_vars[var_name] = EnvVar(
                name=var_name,
                classification=classification,
                default_value=default_value if default_value not in ['__set_in_secret_store__', 'CHANGE_TO_REAL_ALPACA_API_KEY'] else None,
                required=required,
                usage_locations=usage_locations,
                found_in_envs=found_in_envs
            )
        
        print(f"✅ Cataloged {len(self.env_vars)} unique environment variables")
        return self.env_vars
    
    def generate_env_example(self) -> str:
        """Generate .env.example file."""
        lines = [
            "# Environment Variables - Example Configuration",
            "# Copy this file to .env and fill in your values",
            "# DO NOT commit .env with real secrets!\n",
        ]
        
        # Group by classification
        config_vars = [(name, var) for name, var in sorted(self.env_vars.items()) if var.classification == 'config']
        secret_vars = [(name, var) for name, var in sorted(self.env_vars.items()) if var.classification == 'secret']
        
        if config_vars:
            lines.append("# Configuration Variables")
            for name, var in config_vars:
                if var.default_value:
                    lines.append(f"{name}={var.default_value}")
                else:
                    lines.append(f"# {name}=<your_value>")
            lines.append("")
        
        if secret_vars:
            lines.append("# Secrets (NEVER commit real values)")
            for name, var in secret_vars:
                lines.append(f"# {name}=<your_secret_{name.lower()}>")
            lines.append("")
        
        return '\n'.join(lines)
    
    def generate_markdown_report(self) -> str:
        """Generate comprehensive markdown report."""
        lines = [
            "# Environment Variable Catalog",
            f"*Generated: {Path.cwd().name}*\n",
            "## Summary\n",
            f"- **Total Variables:** {len(self.env_vars)}",
            f"- **Secrets:** {sum(1 for v in self.env_vars.values() if v.classification == 'secret')}",
            f"- **Config:** {sum(1 for v in self.env_vars.values() if v.classification == 'config')}",
            f"- **Required:** {sum(1 for v in self.env_vars.values() if v.required)}\n",
            "## Variables by Environment\n",
        ]
        
        # Environment coverage
        for env_file in ['.env', '.env.paper', '.env.staging', '.env.production']:
            count = sum(1 for v in self.env_vars.values() if env_file in v.found_in_envs)
            lines.append(f"- `{env_file}`: {count} variables")
        
        lines.extend([
            "\n## Variable Reference\n",
            "| Variable | Classification | Required | Default | Envs | Usage |",
            "|----------|---------------|----------|---------|------|-------|"
        ])
        
        for name, var in sorted(self.env_vars.items()):
            envs = ', '.join(var.found_in_envs) if var.found_in_envs else 'None'
            usage_count = len(var.usage_locations)
            
            # SECURITY FIX: Redact secret values, show config values
            if var.classification == 'secret':
                default = '[REDACTED - See Secrets Vault]'
            else:
                default = var.default_value[:30] if var.default_value else 'None'
            
            required = '✅' if var.required else ''
            
            lines.append(
                f"| `{name}` | {var.classification} | {required} | `{default}` | {envs} | {usage_count} locations |"
            )
        
        return '\n'.join(lines)


def main():
    """Main execution."""
    root = Path.cwd()
    print(f"🚀 Environment Variable Catalog Generator")
    print(f"📂 Repository: {root}\n")
    
    generator = EnvCatalogGenerator(root)
    env_vars = generator.generate_catalog()
    
    # Generate outputs
    reports_dir = root / 'reports'
    reports_dir.mkdir(exist_ok=True)
    
    # Markdown report
    md_report = generator.generate_markdown_report()
    md_path = reports_dir / 'ENV_CATALOG.md'
    md_path.write_text(md_report, encoding='utf-8')
    print(f"\n✅ Wrote {md_path}")
    
    # .env.example
    env_example = generator.generate_env_example()
    example_path = root / '.env.example'
    example_path.write_text(env_example, encoding='utf-8')
    print(f"✅ Wrote {example_path}")
    
    # JSON export
    json_data = {name: asdict(var) for name, var in env_vars.items()}
    json_path = reports_dir / 'audit' / 'env_catalog.json'
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_data, indent=2), encoding='utf-8')
    print(f"✅ Wrote {json_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("📊 ENVIRONMENT CATALOG SUMMARY")
    print("="*60)
    secrets = [v for v in env_vars.values() if v.classification == 'secret']
    configs = [v for v in env_vars.values() if v.classification == 'config']
    required = [v for v in env_vars.values() if v.required]
    
    print(f"Total Variables:    {len(env_vars)}")
    print(f"  Secrets:          {len(secrets)}")
    print(f"  Config:           {len(configs)}")
    print(f"  Required:         {len(required)}")
    
    print("\n⚠️  Variables classified as SECRETS:")
    for var in sorted(secrets, key=lambda x: x.name)[:10]:
        envs = ', '.join(var.found_in_envs) if var.found_in_envs else 'not in any .env'
        print(f"  • {var.name:40} ({envs})")
    if len(secrets) > 10:
        print(f"  ... and {len(secrets) - 10} more")
    
    print(f"\n✅ Catalog complete. Review: {md_path}")


if __name__ == '__main__':
    main()
