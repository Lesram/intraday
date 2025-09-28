"""
Test Module 91: backend.ml.sentiment
=====================================

Tests for the sentiment module in backend/ml/sentiment.py to achieve 100% coverage.

This module tests:
- Import functionality and re-export behavior
- Module attributes and __all__ exports
- Access to SocialSentimentAnalyzer from the module

Module Under Test: backend/ml/sentiment.py (2 statements)
Coverage Goal: 100% (2/2 statements)
"""

import importlib.util
import pytest
import sys
from pathlib import Path

# Standard import approach for coverage tracking
from backend.ml.sentiment import SocialSentimentAnalyzer
import backend.ml.sentiment as sentiment_module

class TestModule91BackendMlSentiment:
    """
    Test class for backend/ml/sentiment.py module.
    
    This module is a simple re-export wrapper for SocialSentimentAnalyzer
    from backend.data.social_sentiment, so we test the import/export mechanism.
    """
    
    def test_module_import_successful(self):
        """Test that the sentiment module can be imported successfully."""
        # Test direct import
        assert sentiment_module is not None
        
        # Test that the module has expected attributes
        assert hasattr(sentiment_module, 'SocialSentimentAnalyzer')
        assert hasattr(sentiment_module, '__all__')
        
    def test_social_sentiment_analyzer_import(self):
        """Test that SocialSentimentAnalyzer can be imported from the module."""
        # Test direct import from module
        from backend.ml.sentiment import SocialSentimentAnalyzer as ImportedAnalyzer
        
        # Verify it's a class and can be referenced
        assert ImportedAnalyzer is not None
        assert callable(ImportedAnalyzer)
        
        # Test that it's the same class as imported at module level
        assert ImportedAnalyzer is SocialSentimentAnalyzer
        
    def test_module_all_exports(self):
        """Test the __all__ export list contains expected items."""
        # Verify __all__ exists and contains SocialSentimentAnalyzer
        assert hasattr(sentiment_module, '__all__')
        all_exports = getattr(sentiment_module, '__all__')
        
        assert isinstance(all_exports, list)
        assert 'SocialSentimentAnalyzer' in all_exports
        assert len(all_exports) == 1
        
    def test_module_docstring_access(self):
        """Test access to module docstring and metadata."""
        # Test module docstring
        assert sentiment_module.__doc__ is not None
        assert 'Social sentiment analyzer mock' in sentiment_module.__doc__
        assert 'backend/data/social_sentiment.py' in sentiment_module.__doc__
        
    def test_analyzer_class_reference(self):
        """Test that the imported SocialSentimentAnalyzer is properly referenced."""
        # Test class attributes
        analyzer_class = sentiment_module.SocialSentimentAnalyzer
        assert analyzer_class is not None
        
        # Verify it has expected class attributes
        assert hasattr(analyzer_class, '__name__')
        assert analyzer_class.__name__ == 'SocialSentimentAnalyzer'
        
    def test_module_attribute_access(self):
        """Test access to all module attributes."""
        # Test access via getattr
        analyzer_via_getattr = getattr(sentiment_module, 'SocialSentimentAnalyzer')
        assert analyzer_via_getattr is SocialSentimentAnalyzer
        
        # Test all exports are accessible
        all_list = getattr(sentiment_module, '__all__')
        for export_name in all_list:
            assert hasattr(sentiment_module, export_name)
            attr = getattr(sentiment_module, export_name)
            assert attr is not None

class TestModule91Coverage:
    """
    Coverage-focused tests to ensure every line in sentiment.py is executed.
    """
    
    def test_import_line_coverage(self):
        """Test the import line: from backend.data.social_sentiment import SocialSentimentAnalyzer"""
        # This test ensures the import line is executed during coverage
        import backend.ml.sentiment
        
        # Verify the import worked by accessing the class
        assert hasattr(backend.ml.sentiment, 'SocialSentimentAnalyzer')
        
    def test_all_line_coverage(self):
        """Test the __all__ line: __all__ = ["SocialSentimentAnalyzer"]"""
        # This test ensures the __all__ assignment line is executed
        import backend.ml.sentiment as sent_mod
        
        # Verify __all__ was set correctly
        assert hasattr(sent_mod, '__all__')
        assert sent_mod.__all__ == ["SocialSentimentAnalyzer"]

class TestModule91Standalone:
    """
    Standalone tests using importlib to ensure independent coverage.
    """
    
    def test_standalone_module_loading(self):
        """Test loading the module independently to ensure all lines execute."""
        # Get the module path
        module_path = Path(__file__).parent.parent.parent / 'backend' / 'ml' / 'sentiment.py'
        
        # Load module using importlib
        spec = importlib.util.spec_from_file_location('test_sentiment', module_path)
        test_module = importlib.util.module_from_spec(spec)
        
        # Execute the module (this covers all lines)
        spec.loader.exec_module(test_module)
        
        # Verify module loaded correctly
        assert hasattr(test_module, 'SocialSentimentAnalyzer')
        assert hasattr(test_module, '__all__')
        assert test_module.__all__ == ["SocialSentimentAnalyzer"]

class TestModule91Integration:
    """
    Integration tests to verify the sentiment module works with the broader system.
    """
    
    def test_import_star_functionality(self):
        """Test that 'from backend.ml.sentiment import *' works correctly."""
        # This is essentially what happens with 'import *'
        import backend.ml.sentiment as sent_mod
        
        # Get all exported items
        all_items = getattr(sent_mod, '__all__', [])
        
        for item in all_items:
            # Verify each item in __all__ is accessible
            assert hasattr(sent_mod, item)
            imported_item = getattr(sent_mod, item)
            assert imported_item is not None
            
    def test_module_in_package_context(self):
        """Test the module works correctly within the backend.ml package."""
        # Test that the module can be accessed through the package hierarchy
        import backend.ml
        
        # Check if the sentiment module is accessible
        if hasattr(backend.ml, 'sentiment'):
            sentiment_submodule = backend.ml.sentiment
            assert hasattr(sentiment_submodule, 'SocialSentimentAnalyzer')

# Edge case and error handling tests
class TestModule91EdgeCases:
    """
    Edge case tests for comprehensive coverage.
    """
    
    def test_analyzer_class_properties(self):
        """Test properties of the SocialSentimentAnalyzer class."""
        from backend.ml.sentiment import SocialSentimentAnalyzer
        
        # Test class properties
        assert SocialSentimentAnalyzer.__module__ == 'backend.data.social_sentiment'
        assert hasattr(SocialSentimentAnalyzer, '__init__')
        
    def test_module_metadata(self):
        """Test module metadata and special attributes."""
        import backend.ml.sentiment as sent_mod
        
        # Test special module attributes
        assert hasattr(sent_mod, '__file__')
        assert hasattr(sent_mod, '__name__')
        assert sent_mod.__name__ == 'backend.ml.sentiment'
        
    def test_multiple_import_consistency(self):
        """Test that multiple imports of the module are consistent."""
        import backend.ml.sentiment as sent1
        import backend.ml.sentiment as sent2
        
        # Both imports should reference the same module
        assert sent1 is sent2
        assert sent1.SocialSentimentAnalyzer is sent2.SocialSentimentAnalyzer
        assert sent1.__all__ == sent2.__all__