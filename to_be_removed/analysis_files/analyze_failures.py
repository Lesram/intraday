#!/usr/bin/env python3
"""Analyze test failure patterns from batch results."""

import xml.etree.ElementTree as ET
import glob
from collections import Counter

def analyze_failures():
    attr_errors = []
    import_errors = []
    type_errors = []
    other_errors = []
    
    print("🔍 ANALYZING FAILURE PATTERNS FROM BATCH RESULTS")
    print("=" * 60)
    
    xml_files = glob.glob('batch_*_results.xml')
    print(f"Found {len(xml_files)} batch result files")
    
    for xml_file in xml_files[:15]:  # Analyze first 15 batch files
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            for failure in root.findall('.//failure'):
                msg = failure.get('message', '')
                if not msg:
                    continue
                    
                if 'AttributeError' in msg and 'has no attribute' in msg:
                    attr_errors.append(msg)
                elif 'ImportError' in msg or 'ModuleNotFoundError' in msg:
                    import_errors.append(msg)
                elif 'TypeError' in msg:
                    type_errors.append(msg)
                else:
                    other_errors.append(msg)
                    
        except Exception as e:
            print(f"Error processing {xml_file}: {e}")
    
    print(f"\n📊 FAILURE SUMMARY:")
    print(f"   AttributeErrors: {len(attr_errors)}")
    print(f"   ImportErrors: {len(import_errors)}")
    print(f"   TypeErrors: {len(type_errors)}")
    print(f"   Other errors: {len(other_errors)}")
    
    print(f"\n🚨 TOP ATTRIBUTEERRORS:")
    for i, err in enumerate(attr_errors[:5]):
        print(f"   {i+1}. {err[:120]}...")
        
    print(f"\n📦 TOP IMPORTERRORS:")
    for i, err in enumerate(import_errors[:3]):
        print(f"   {i+1}. {err[:120]}...")
        
    print(f"\n🔧 TOP TYPEERRORS:")
    for i, err in enumerate(type_errors[:3]):
        print(f"   {i+1}. {err[:120]}...")

if __name__ == "__main__":
    analyze_failures()
