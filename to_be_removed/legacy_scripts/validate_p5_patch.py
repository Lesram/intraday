#!/usr/bin/env python3
"""
P5 Patch Validation: Order Services Constructor Shims
Tests kwargs tolerance for OrderStateMachine, OrderIntegrityService, and OrderService
"""

import sys
import traceback

def main():
    print("🔍 P5 Patch Validation: Order Services Constructor Shims")
    print("=" * 65)
    
    success_count = 0
    total_tests = 6
    
    try:
        # Test 1: OrderStateMachine with audit_logger
        print("\n✅ Test 1: OrderStateMachine with audit_logger")
        from backend.models.order_integrity import OrderStateMachine
        
        def mock_logger(*args, **kwargs):
            pass
            
        fsm1 = OrderStateMachine(audit_logger=mock_logger)
        assert fsm1.audit_logger == mock_logger, "audit_logger should be set correctly"
        print("   ✅ OrderStateMachine with audit_logger works")
        success_count += 1
        
        # Test 2: OrderStateMachine without audit_logger (default)
        print("\n✅ Test 2: OrderStateMachine default audit_logger")
        
        fsm2 = OrderStateMachine()
        assert callable(fsm2.audit_logger), "Default audit_logger should be callable"
        # Test the default logger doesn't crash
        fsm2.audit_logger("test", key="value")
        print("   ✅ OrderStateMachine default audit_logger works")
        success_count += 1
        
        # Test 3: OrderStateMachine with extra kwargs
        print("\n✅ Test 3: OrderStateMachine with extra kwargs")
        
        fsm3 = OrderStateMachine(audit_logger=mock_logger, extra_param="test", another_param=123)
        assert fsm3.audit_logger == mock_logger, "audit_logger should be set with extra kwargs"
        print("   ✅ OrderStateMachine with extra kwargs works")
        success_count += 1
        
        # Test 4: OrderIntegrityService with db_session
        print("\n✅ Test 4: OrderIntegrityService with db_session")
        from backend.models.order_integrity import OrderIntegrityService
        
        class MockSession:
            pass
            
        mock_session = MockSession()
        integrity1 = OrderIntegrityService(db_session=mock_session)
        assert integrity1.db_session == mock_session, "db_session should be set correctly"
        print("   ✅ OrderIntegrityService with db_session works")
        success_count += 1
        
        # Test 5: OrderIntegrityService without db_session (default)
        print("\n✅ Test 5: OrderIntegrityService default db_session")
        
        integrity2 = OrderIntegrityService()
        assert integrity2.db_session is None, "Default db_session should be None"
        print("   ✅ OrderIntegrityService default db_session works")
        success_count += 1
        
        # Test 6: OrderService with db_session and kwargs
        print("\n✅ Test 6: OrderService with db_session")
        from backend.services.order_service import OrderService
        
        service1 = OrderService(db_session=mock_session, extra_param="test")
        assert service1.db_session == mock_session, "db_session should be set correctly"
        print("   ✅ OrderService with db_session and kwargs works")
        success_count += 1
        
    except Exception as e:
        print(f"\n❌ P5 PATCH VALIDATION FAILED!")
        print(f"Error: {str(e)}")
        print(f"Tests Passed: {success_count}/{total_tests}")
        traceback.print_exc()
        return False
    
    if success_count == total_tests:
        print(f"\n🎯 P5 PATCH VALIDATION: COMPLETE")
        print(f"✅ Tests Passed: {success_count}/{total_tests}")
        print(f"\n📋 P5 Implementation Summary:")
        print(f"   ✅ OrderStateMachine: kwargs tolerant constructor")
        print(f"   ✅ OrderIntegrityService: kwargs tolerant constructor")  
        print(f"   ✅ OrderService: kwargs tolerant constructor")
        print(f"   ✅ All constructors handle missing/extra parameters")
        print(f"   ✅ Default value handling working correctly")
        print(f"\n🚀 P5 patch successfully implements service constructor shims!")
        return True
    else:
        print(f"\n❌ P5 PATCH VALIDATION INCOMPLETE")
        print(f"Tests Passed: {success_count}/{total_tests}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
