"""
Comprehensive light mode integration test.
Tests actual backend modules to ensure they work in light mode.
"""

# Activate light mode FIRST
import conftest_light_mode

def test_backend_modules_light_mode():
    """Test that backend modules work properly in light mode"""
    print("\n🧪 Testing Backend Modules in Light Mode:")
    
    # Test social sentiment module
    try:
        from backend.data.social_sentiment import NLP_AVAILABLE, SocialSentimentAnalyzer
        print(f"   ✅ social_sentiment imported - NLP_AVAILABLE: {NLP_AVAILABLE}")
        
        # Test analyzer creation in light mode
        analyzer = SocialSentimentAnalyzer()
        print(f"   ✅ SocialSentimentAnalyzer created successfully")
    except Exception as e:
        print(f"   ❌ social_sentiment error: {e}")
        return False
    
    # Test ensemble model
    try:
        from backend.models.ensemble_model import EnsembleModel
        print(f"   ✅ ensemble_model imported successfully")
        
        # Try to create instance 
        model = EnsembleModel()
        print(f"   ✅ EnsembleModel instance created")
    except Exception as e:
        print(f"   ❌ ensemble_model error: {e}")
        return False
    
    print("   🎉 All backend modules working in light mode!")
    return True

def test_api_imports():
    """Test that API modules can be imported"""
    print("\n🌐 Testing API Imports in Light Mode:")
    
    try:
        from backend.api.main import app
        print(f"   ✅ FastAPI app imported successfully")
        
        from backend.api.auth import router as auth_router
        print(f"   ✅ Auth router imported successfully")
        
        from backend.api.portfolio import router as portfolio_router
        print(f"   ✅ Portfolio router imported successfully")
        
    except Exception as e:
        print(f"   ❌ API import error: {e}")
        return False
    
    print("   🎉 All API modules working in light mode!")
    return True

if __name__ == "__main__":
    success = True
    success &= test_backend_modules_light_mode()
    success &= test_api_imports()
    
    if success:
        print("\n✅ COMPREHENSIVE LIGHT MODE TEST PASSED!")
        print("   🚀 System ready for pytest execution")
    else:
        print("\n❌ LIGHT MODE TEST FAILED!")
        exit(1)
