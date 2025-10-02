#!/usr/bin/env python3
"""
Platform Cleanup Audit Tool - Phase A: Inventory & Topology
Generates comprehensive file inventory and Python import graph analysis.
"""

import ast
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
import re


@dataclass
class FileInfo:
    """Metadata about a file in the repository."""
    path: str
    size: int
    ext: str
    last_modified: str
    category: str  # source, test, config, doc, artifact, generated
    

@dataclass
class ImportNode:
    """Represents a Python module and its imports."""
    path: str
    imports: List[str]
    imported_by: List[str]
    is_entrypoint: bool
    is_orphan: bool


class PlatformAuditor:
    """Comprehensive platform audit and cleanup tool."""
    
    def __init__(self, root_dir: Path):
        self.root = root_dir
        self.files: List[FileInfo] = []
        self.import_graph: Dict[str, ImportNode] = {}
        self.entrypoints = [
            'main.py',
            'backend/api/main.py',
            'backend/api/factory.py',
            'backend/infra/outbox_worker.py'
        ]
        
        # Directories to exclude from scan
        self.exclude_dirs = {
            '__pycache__', '.pytest_cache', 'htmlcov', '.git', 
            'venv', '.venv', 'node_modules', '.eggs', '.tox',
            'archive', 'backups', 'test_results'
        }
        
        # Patterns for identifying file categories
        self.test_patterns = re.compile(r'(test_.*\.py|.*_test\.py|conftest\.py)')
        self.config_extensions = {'.yaml', '.yml', '.json', '.toml', '.ini', '.env'}
        self.doc_extensions = {'.md', '.rst', '.txt'}
        self.artifact_patterns = re.compile(r'.*\.(log|pyc|pyo|coverage|cache)$')
        
    def categorize_file(self, path: Path) -> str:
        """Categorize a file based on its characteristics."""
        str_path = str(path)
        
        if self.artifact_patterns.match(str_path):
            return 'artifact'
        if self.test_patterns.match(path.name):
            return 'test'
        if path.suffix in self.config_extensions:
            return 'config'
        if path.suffix in self.doc_extensions:
            return 'doc'
        if path.suffix == '.py':
            # Check if in test directory
            if 'test' in path.parts:
                return 'test'
            return 'source'
        if path.name.startswith('.'):
            return 'config'
        
        return 'other'
    
    def scan_files(self) -> List[FileInfo]:
        """Generate comprehensive file inventory."""
        print("📁 Scanning repository files...")
        
        for root, dirs, files in os.walk(self.root):
            # Remove excluded directories from traversal
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            root_path = Path(root)
            for file in files:
                file_path = root_path / file
                try:
                    stat = file_path.stat()
                    rel_path = file_path.relative_to(self.root)
                    
                    file_info = FileInfo(
                        path=str(rel_path).replace('\\', '/'),
                        size=stat.st_size,
                        ext=file_path.suffix,
                        last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        category=self.categorize_file(file_path)
                    )
                    self.files.append(file_info)
                    
                except (PermissionError, OSError) as e:
                    print(f"⚠️  Skipping {file_path}: {e}")
        
        print(f"✅ Found {len(self.files)} files")
        return self.files
    
    def extract_imports(self, file_path: Path) -> Set[str]:
        """Extract import statements from a Python file."""
        imports = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                        
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        # Handle relative imports
                        if node.level > 0:
                            # Convert relative to absolute based on file location
                            parts = file_path.parts
                            if 'backend' in parts:
                                idx = parts.index('backend')
                                base = '.'.join(parts[idx:idx+node.level+1])
                                module = f"{base}.{node.module}" if node.module else base
                                imports.add(module.split('.')[0])
                        else:
                            imports.add(node.module.split('.')[0])
                            
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"⚠️  Could not parse {file_path}: {e}")
        
        return imports
    
    def build_import_graph(self) -> Dict[str, ImportNode]:
        """Build Python import dependency graph."""
        print("\n🔗 Building import graph...")
        
        # First pass: collect all Python modules
        python_files = [f for f in self.files if f.ext == '.py' and f.category != 'artifact']
        
        module_to_path = {}
        for file in python_files:
            # Convert file path to module name
            module = file.path.replace('/', '.').replace('.py', '')
            if module.startswith('backend.'):
                module_to_path[module.split('.')[1]] = file.path
            else:
                module_to_path[module.split('.')[0]] = file.path
        
        # Second pass: extract imports and build graph
        for file in python_files:
            file_path = self.root / file.path
            imports = self.extract_imports(file_path)
            
            # Filter to local imports only
            local_imports = [imp for imp in imports if imp in module_to_path]
            
            node = ImportNode(
                path=file.path,
                imports=local_imports,
                imported_by=[],
                is_entrypoint=file.path in self.entrypoints,
                is_orphan=False
            )
            
            self.import_graph[file.path] = node
        
        # Third pass: populate imported_by relationships
        for path, node in self.import_graph.items():
            for imported in node.imports:
                if imported in module_to_path:
                    imported_path = module_to_path[imported]
                    if imported_path in self.import_graph:
                        self.import_graph[imported_path].imported_by.append(path)
        
        print(f"✅ Built graph with {len(self.import_graph)} nodes")
        return self.import_graph
    
    def find_orphans(self) -> List[str]:
        """Identify orphaned files (not reachable from entrypoints)."""
        print("\n🔍 Identifying orphaned modules...")
        
        reachable = set()
        to_visit = [node.path for node in self.import_graph.values() if node.is_entrypoint]
        
        while to_visit:
            current = to_visit.pop()
            if current in reachable:
                continue
            
            reachable.add(current)
            
            if current in self.import_graph:
                node = self.import_graph[current]
                # Add all imports to visit queue
                for imp in node.imports:
                    # Find actual file path for this import
                    for path, n in self.import_graph.items():
                        if path not in reachable and imp in path:
                            to_visit.append(path)
        
        # Mark orphans
        orphans = []
        for path, node in self.import_graph.items():
            if path not in reachable and not node.is_entrypoint:
                node.is_orphan = True
                # Exclude test files from orphan detection
                if '/test/' not in path and not path.startswith('test'):
                    orphans.append(path)
        
        print(f"✅ Found {len(orphans)} orphaned modules")
        return orphans
    
    def find_code_smells(self) -> Dict[str, List[Tuple[str, int]]]:
        """Find code smells: TODOs, FIXMEs, pdb, NotImplementedError, etc."""
        print("\n🔎 Scanning for code smells...")
        
        smells = defaultdict(list)
        patterns = {
            'TODO': re.compile(r'#\s*TODO:', re.IGNORECASE),
            'FIXME': re.compile(r'#\s*FIXME:', re.IGNORECASE),
            'XXX': re.compile(r'#\s*XXX:', re.IGNORECASE),
            'HACK': re.compile(r'#\s*HACK:', re.IGNORECASE),
            'pdb': re.compile(r'\bpdb\.set_trace\(\)'),
            'breakpoint': re.compile(r'\bbreakpoint\(\)'),
            'NotImplemented': re.compile(r'raise\s+NotImplementedError'),
            'print_debug': re.compile(r'\bprint\s*\(.*#.*debug', re.IGNORECASE),
        }
        
        python_files = [f for f in self.files if f.ext == '.py' and f.category != 'test']
        
        for file in python_files:
            file_path = self.root / file.path
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        for smell_type, pattern in patterns.items():
                            if pattern.search(line):
                                smells[smell_type].append((file.path, line_num))
            except (UnicodeDecodeError, PermissionError):
                pass
        
        total = sum(len(v) for v in smells.values())
        print(f"✅ Found {total} code smell instances")
        return dict(smells)
    
    def generate_report(self, output_dir: Path):
        """Generate comprehensive audit report."""
        print(f"\n📊 Generating reports in {output_dir}...")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # File inventory JSON
        inventory_path = output_dir / 'file_inventory.json'
        with open(inventory_path, 'w') as f:
            json.dump([asdict(fi) for fi in self.files], f, indent=2)
        print(f"✅ Wrote {inventory_path}")
        
        # Import graph JSON
        graph_path = output_dir / 'import_graph.json'
        graph_data = {
            path: {
                'imports': node.imports,
                'imported_by': node.imported_by,
                'is_entrypoint': node.is_entrypoint,
                'is_orphan': node.is_orphan
            }
            for path, node in self.import_graph.items()
        }
        with open(graph_path, 'w') as f:
            json.dump(graph_data, f, indent=2)
        print(f"✅ Wrote {graph_path}")
        
        # Summary statistics
        stats = {
            'total_files': len(self.files),
            'total_size_mb': sum(f.size for f in self.files) / (1024 * 1024),
            'by_category': {},
            'by_extension': {},
            'orphaned_modules': len([n for n in self.import_graph.values() if n.is_orphan]),
            'entrypoints': len([n for n in self.import_graph.values() if n.is_entrypoint]),
        }
        
        for file in self.files:
            stats['by_category'][file.category] = stats['by_category'].get(file.category, 0) + 1
            stats['by_extension'][file.ext] = stats['by_extension'].get(file.ext, 0) + 1
        
        stats_path = output_dir / 'audit_stats.json'
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"✅ Wrote {stats_path}")
        
        return stats


def main():
    """Main execution."""
    root = Path.cwd()
    print(f"🚀 Platform Cleanup Audit Tool")
    print(f"📂 Repository: {root}\n")
    
    auditor = PlatformAuditor(root)
    
    # Phase A tasks
    auditor.scan_files()
    auditor.build_import_graph()
    orphans = auditor.find_orphans()
    smells = auditor.find_code_smells()
    
    # Generate reports
    reports_dir = root / 'reports' / 'audit'
    stats = auditor.generate_report(reports_dir)
    
    # Print summary
    print("\n" + "="*60)
    print("📈 AUDIT SUMMARY")
    print("="*60)
    print(f"Total Files:        {stats['total_files']:,}")
    print(f"Total Size:         {stats['total_size_mb']:.2f} MB")
    print(f"Python Modules:     {stats['by_extension'].get('.py', 0):,}")
    print(f"Orphaned Modules:   {stats['orphaned_modules']}")
    print(f"Entrypoints:        {stats['entrypoints']}")
    print("\nBy Category:")
    for cat, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
        print(f"  {cat:12} {count:6,}")
    
    print("\nCode Smells:")
    for smell, instances in sorted(smells.items(), key=lambda x: -len(x[1])):
        print(f"  {smell:15} {len(instances):4} occurrences")
    
    print(f"\n✅ Audit complete. Reports in: {reports_dir}")
    
    if orphans:
        print(f"\n⚠️  Found {len(orphans)} orphaned files - review recommended")


if __name__ == '__main__':
    main()
