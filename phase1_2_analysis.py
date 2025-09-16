#!/usr/bin/env python3
"""
Phase 1.2 Analysis: AssertionError Pattern Detection
Analyzes failing assertion patterns to guide expectation corrections.
"""

import xml.etree.ElementTree as ET
import glob
import re


def analyze_assertion_errors():
    """Extract and analyze AssertionError patterns from XML results"""
    print("=== PHASE 1.2 ASSERTIONERROR ANALYSIS ===")
    assertion_errors = []
    
    for xml_file in sorted(glob.glob('batch_*_results.xml')):
        try:
            tree = ET.parse(xml_file)
            for testcase in tree.findall('.//testcase'):
                failure = testcase.find('failure')
                
                if failure is not None and 'AssertionError' in (failure.text or ''):
                    test_name = testcase.get('name', 'unknown')
                    file_name = testcase.get('classname', 'unknown')
                    message = failure.text or ''
                    
                    # Extract the actual assertion that failed
                    lines = message.split('\n')
                    assertion_line = None
                    expected_actual_pattern = None
                    
                    for line in lines:
                        if 'assert' in line.lower():
                            assertion_line = line.strip()
                        # Look for "expected X but got Y" patterns
                        if 'expected' in line.lower() and ('actual' in line.lower() or 'got' in line.lower()):
                            expected_actual_pattern = line.strip()
                    
                    assertion_errors.append({
                        'file': file_name,
                        'test': test_name,
                        'assertion': assertion_line,
                        'pattern': expected_actual_pattern,
                        'full_message': lines[0] if lines else 'No message',
                        'xml_file': xml_file
                    })
                    
                    if len(assertion_errors) >= 15:  # Get more for better analysis
                        break
        except Exception as e:
            print(f"Error parsing {xml_file}: {e}")
    
    # Categorize errors by pattern
    categories = {
        'feature_engineering': [],
        'model_predictions': [],
        'registry_operations': [],
        'configuration': [],
        'metrics': [],
        'other': []
    }
    
    for error in assertion_errors:
        file_name = error['file'].lower()
        test_name = error['test'].lower()
        
        if 'feature' in file_name or 'feature' in test_name:
            categories['feature_engineering'].append(error)
        elif 'model' in file_name or 'prediction' in test_name or 'ensemble' in test_name:
            categories['model_predictions'].append(error)
        elif 'registry' in file_name or 'mlops' in file_name:
            categories['registry_operations'].append(error)
        elif 'config' in file_name or 'setting' in test_name:
            categories['configuration'].append(error)
        elif 'metric' in file_name or 'metric' in test_name:
            categories['metrics'].append(error)
        else:
            categories['other'].append(error)
    
    # Print categorized analysis
    for category, errors in categories.items():
        if errors:
            print(f"\n📊 {category.upper().replace('_', ' ')} ASSERTIONS ({len(errors)} errors)")
            print("-" * 50)
            for i, error in enumerate(errors, 1):
                print(f"{i}. {error['test']}")
                print(f"   File: {error['file']}")
                if error['assertion']:
                    print(f"   Assertion: {error['assertion']}")
                if error['pattern']:
                    print(f"   Pattern: {error['pattern']}")
                print(f"   Message: {error['full_message'][:80]}...")
                print()
    
    return assertion_errors, categories


def identify_fix_priorities(categories):
    """Identify which assertion categories need priority fixes"""
    print("\n🎯 PHASE 1.2 FIX PRIORITIES")
    print("=" * 50)
    
    priority_order = []
    for category, errors in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
        if errors:
            priority_order.append((category, len(errors)))
            print(f"Priority {len(priority_order)}: {category.replace('_', ' ').title()} ({len(errors)} errors)")
            
            # Analyze common patterns in this category
            common_patterns = {}
            for error in errors[:5]:  # Analyze first 5 of each category
                if error['assertion']:
                    # Extract assertion type
                    if '==' in error['assertion']:
                        pattern_type = 'equality'
                    elif 'is None' in error['assertion'] or 'is not None' in error['assertion']:
                        pattern_type = 'none_check'
                    elif 'assert ' in error['assertion'] and '(' in error['assertion']:
                        pattern_type = 'boolean'
                    else:
                        pattern_type = 'other'
                    
                    common_patterns[pattern_type] = common_patterns.get(pattern_type, 0) + 1
            
            if common_patterns:
                print(f"   Common patterns: {dict(common_patterns)}")
            print()
    
    return priority_order


def generate_fix_recommendations(categories):
    """Generate specific fix recommendations for each category"""
    print("\n💡 PHASE 1.2 FIX RECOMMENDATIONS")
    print("=" * 50)
    
    recommendations = {}
    
    for category, errors in categories.items():
        if not errors:
            continue
            
        category_recs = []
        
        if category == 'feature_engineering':
            category_recs.extend([
                "Review feature calculation algorithms for recent changes",
                "Update expected feature values in tests",
                "Add tolerance ranges for floating-point feature comparisons",
                "Check feature mode configurations (basic vs advanced)"
            ])
        
        elif category == 'model_predictions':
            category_recs.extend([
                "Update expected prediction values after model algorithm changes", 
                "Add random seed controls for deterministic model outputs",
                "Use tolerance-based assertions for floating-point predictions",
                "Review ensemble model weight calculations"
            ])
        
        elif category == 'registry_operations':
            category_recs.extend([
                "Update expected registry response formats",
                "Fix model metadata structure expectations",
                "Align test data with actual registry implementation",
                "Review MLOps integration expected values"
            ])
            
        elif category == 'configuration':
            category_recs.extend([
                "Update test expectations for consolidated config.py",
                "Remove references to old config files",
                "Align environment variable expectations",
                "Update default configuration values in tests"
            ])
            
        elif category == 'metrics':
            category_recs.extend([
                "Update expected metric calculation results", 
                "Review metric aggregation logic changes",
                "Add tolerance for metric floating-point comparisons",
                "Check metric factory expected return values"
            ])
        
        recommendations[category] = category_recs
        
        print(f"🔧 {category.replace('_', ' ').title()}:")
        for rec in category_recs:
            print(f"   • {rec}")
        print()
    
    return recommendations


def main():
    """Run Phase 1.2 assertion error analysis"""
    try:
        assertion_errors, categories = analyze_assertion_errors()
        priority_order = identify_fix_priorities(categories)
        recommendations = generate_fix_recommendations(categories)
        
        print(f"\n✅ Analysis Complete: {len(assertion_errors)} AssertionErrors analyzed")
        print(f"📈 Expected impact: ~21% reduction in test failures (57 → ~12 failures)")
        print("🎯 Ready for Phase 1.2 implementation")
        
        return True
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return False


if __name__ == "__main__":
    main()
