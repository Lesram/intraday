#!/usr/bin/env python3
"""
Codebase Cleanup Analysis Tool
Identifies potentially unused Python files and other cleanup candidates
"""

import os
import glob
import re
from pathlib import Path
from datetime import datetime, timedelta
import ast
import subprocess

class CodebaseAnalyzer:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.python_files = []
        self.imports_map = {}
        self.suspicious_files = {
            'legacy_modules': [],
            'one_off_outputs': [],
            'test_artifacts': [], 
            'old_files': []
        }
        
    def scan_python_files(self):
        """Find all Python files in the project"""
        patterns = ['**/*.py']
        for pattern in patterns:
            for file_path in self.project_root.glob(pattern):
                # Skip the to_be_removed directory and __pycache__
                if 'to_be_removed' not in str(file_path) and '__pycache__' not in str(file_path):
                    self.python_files.append(file_path)
        print(f"Found {len(self.python_files)} Python files")
        
    def analyze_imports(self):
        """Analyze which Python files are imported by others"""
        print("Analyzing imports...")
        
        # Build map of what imports what
        for file_path in self.python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Find import statements
                imports = self.extract_imports(content)
                self.imports_map[str(file_path)] = imports
                
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                
    def extract_imports(self, content):
        """Extract import statements from Python code"""
        imports = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                        for alias in node.names:
                            imports.append(f"{node.module}.{alias.name}")
        except:
            # Fallback to regex if AST parsing fails
            import_patterns = [
                r'^\s*import\s+([a-zA-Z_][a-zA-Z0-9_\.]*)',
                r'^\s*from\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s+import'
            ]
            for pattern in import_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                imports.extend(matches)
                
        return imports
    
    def find_unreferenced_modules(self):
        """Find Python modules that are never imported"""
        print("Finding unreferenced modules...")
        
        # Get all module names (without .py extension and convert paths)
        module_names = set()
        for file_path in self.python_files:
            rel_path = file_path.relative_to(self.project_root)
            # Convert file path to module path
            module_path = str(rel_path).replace('\\', '.').replace('/', '.').replace('.py', '')
            module_names.add(module_path)
            
            # Also add just the filename without extension
            module_names.add(file_path.stem)
            
        # Collect all imports
        all_imports = set()
        for imports in self.imports_map.values():
            for imp in imports:
                all_imports.add(imp)
                # Add partial imports too
                if '.' in imp:
                    parts = imp.split('.')
                    for i in range(1, len(parts) + 1):
                        all_imports.add('.'.join(parts[:i]))
        
        # Find unreferenced modules
        unreferenced = []
        for file_path in self.python_files:
            rel_path = file_path.relative_to(self.project_root)
            module_path = str(rel_path).replace('\\', '.').replace('/', '.').replace('.py', '')
            filename = file_path.stem
            
            # Check if this module is imported anywhere
            is_referenced = False
            for imp in all_imports:
                if (imp == module_path or 
                    imp == filename or 
                    imp.endswith('.' + filename) or
                    module_path.endswith('.' + imp)):
                    is_referenced = True
                    break
                    
            # Special cases that should not be considered unreferenced
            special_cases = [
                '__init__', 'main', 'app', 'conftest', 'setup', 
                'manage', 'wsgi', 'asgi', 'settings'
            ]
            
            if (not is_referenced and 
                filename not in special_cases and
                not filename.startswith('test_') and
                not str(file_path).endswith('__main__.py')):
                unreferenced.append(file_path)
                
        return unreferenced
    
    def find_legacy_patterns(self):
        """Find files with legacy naming patterns"""
        patterns = ['*old*', '*legacy*', '*backup*', '*bak*', '*temp*', '*tmp*']
        legacy_files = []
        
        for pattern in patterns:
            for file_path in self.project_root.glob(f'**/{pattern}'):
                if ('to_be_removed' not in str(file_path) and 
                    '__pycache__' not in str(file_path) and
                    file_path.is_file()):
                    legacy_files.append(file_path)
                    
        return legacy_files
    
    def find_one_off_outputs(self):
        """Find generated reports, logs, and other output files"""
        output_patterns = [
            '*.html', '*.pdf', '*.csv', '*.xlsx', '*.xml', 
            '*.log', '*.txt', '*.md', '*.json'
        ]
        
        output_files = []
        for pattern in output_patterns:
            for file_path in self.project_root.glob(f'**/{pattern}'):
                if ('to_be_removed' not in str(file_path) and 
                    '__pycache__' not in str(file_path) and
                    file_path.is_file()):
                    
                    # Check if it looks like a generated file
                    name = file_path.name.lower()
                    suspicious_keywords = [
                        'report', 'summary', 'analysis', 'results', 'output',
                        'export', 'dump', 'cache', 'coverage', 'test_results',
                        'batch_', '_results', 'temp_', 'debug_'
                    ]
                    
                    if any(keyword in name for keyword in suspicious_keywords):
                        # Additional check: is it referenced in code?
                        is_referenced = self.is_file_referenced_in_code(file_path)
                        if not is_referenced:
                            output_files.append(file_path)
                            
        return output_files
    
    def is_file_referenced_in_code(self, file_path):
        """Check if a file is referenced in any Python code"""
        filename = file_path.name
        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if filename in content:
                        return True
            except:
                continue
        return False
    
    def find_old_files(self, days_old=730):  # 2 years
        """Find very old files that haven't been modified"""
        cutoff_date = datetime.now() - timedelta(days=days_old)
        old_files = []
        
        for file_path in self.project_root.glob('**/*'):
            if (file_path.is_file() and 
                'to_be_removed' not in str(file_path) and 
                '__pycache__' not in str(file_path)):
                
                try:
                    mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mod_time < cutoff_date:
                        old_files.append((file_path, mod_time))
                except:
                    continue
                    
        return sorted(old_files, key=lambda x: x[1])
    
    def analyze(self):
        """Run complete analysis"""
        print("Starting codebase analysis...")
        
        self.scan_python_files()
        self.analyze_imports()
        
        print("\n" + "="*60)
        print("ANALYSIS RESULTS")
        print("="*60)
        
        # Unreferenced Python modules
        unreferenced = self.find_unreferenced_modules()
        print(f"\n🔍 UNREFERENCED PYTHON MODULES ({len(unreferenced)}):")
        for file_path in unreferenced:
            print(f"  - {file_path.relative_to(self.project_root)}")
            self.suspicious_files['legacy_modules'].append(file_path)
        
        # Legacy pattern files
        legacy = self.find_legacy_patterns()
        print(f"\n📜 LEGACY PATTERN FILES ({len(legacy)}):")
        for file_path in legacy:
            print(f"  - {file_path.relative_to(self.project_root)}")
            self.suspicious_files['legacy_modules'].append(file_path)
        
        # One-off output files
        outputs = self.find_one_off_outputs()
        print(f"\n📊 POTENTIAL OUTPUT FILES ({len(outputs)}):")
        for file_path in outputs:
            print(f"  - {file_path.relative_to(self.project_root)}")
            self.suspicious_files['one_off_outputs'].append(file_path)
        
        # Old files
        old_files = self.find_old_files()
        print(f"\n📅 OLD FILES (2+ years, {len(old_files)}):")
        for file_path, mod_time in old_files[:20]:  # Show first 20
            print(f"  - {file_path.relative_to(self.project_root)} (modified: {mod_time.strftime('%Y-%m-%d')})")
            self.suspicious_files['old_files'].append(file_path)
        
        if len(old_files) > 20:
            print(f"  ... and {len(old_files) - 20} more")
        
        print(f"\n📋 SUMMARY:")
        print(f"  Legacy modules: {len(self.suspicious_files['legacy_modules'])}")
        print(f"  Output files: {len(self.suspicious_files['one_off_outputs'])}")
        print(f"  Old files: {len(self.suspicious_files['old_files'])}")
        print(f"  Total files for review: {sum(len(files) for files in self.suspicious_files.values())}")
        
        return self.suspicious_files

if __name__ == "__main__":
    analyzer = CodebaseAnalyzer(".")
    results = analyzer.analyze()