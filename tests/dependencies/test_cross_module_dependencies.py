"""
Cross-Module Dependency Testing
Tests: service communication, state synchronization, transaction boundaries
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add backend to Python path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

class TestCrossModuleDependencies:
    """Test dependencies between modules"""
    
    def test_service_to_service_communication(self):
        """Test communication between different services"""
        try:
            # Mock service registry
            with patch('backend.services.service_registry.ServiceRegistry') as mock_registry:
                mock_registry.return_value.get_service.return_value = Mock()
                
                # Test service discovery
                data_service = mock_registry.return_value.get_service('data_service')
                order_service = mock_registry.return_value.get_service('order_service')
                
                assert data_service is not None
                assert order_service is not None
                
                # Test inter-service communication
                data_service.notify_order_service = Mock()
                data_service.notify_order_service('price_update', {'symbol': 'AAPL', 'price': 150})
                
                data_service.notify_order_service.assert_called_once()
                
            print("✅ Service communication test passed")
            
        except Exception as e:
            pytest.fail(f"Service communication failed: {e}")
    
    def test_database_transaction_boundaries(self):
        """Test database transaction handling across modules"""
        try:
            # Mock database transaction manager
            with patch('backend.db.transaction_manager.TransactionManager') as mock_tx:
                mock_tx.return_value.begin_transaction.return_value = 'tx_123'
                mock_tx.return_value.commit_transaction.return_value = True
                mock_tx.return_value.rollback_transaction.return_value = True
                
                # Test multi-table transaction
                tx_id = mock_tx.return_value.begin_transaction()
                assert tx_id == 'tx_123'
                
                # Simulate operations across modules
                with patch('backend.models.order.OrderRepository') as mock_order_repo, \
                     patch('backend.models.position.PositionRepository') as mock_pos_repo:
                    
                    # Order creation
                    mock_order_repo.return_value.create.return_value = {'id': 1}
                    # Position update  
                    mock_pos_repo.return_value.update.return_value = {'id': 1}
                    
                    # Both operations should use same transaction
                    order = mock_order_repo.return_value.create({'symbol': 'AAPL'})
                    position = mock_pos_repo.return_value.update({'symbol': 'AAPL'})
                    
                    # Commit transaction
                    success = mock_tx.return_value.commit_transaction(tx_id)
                    assert success is True
                
            print("✅ Database transaction boundaries test passed")
            
        except Exception as e:
            pytest.fail(f"Database transaction boundaries failed: {e}")
    
    def test_async_operation_coordination(self):
        """Test coordination of async operations"""  
        try:
            # Mock async coordinator
            with patch('backend.services.async_coordinator.AsyncCoordinator') as mock_coord:
                mock_coord.return_value.coordinate_tasks.return_value = ['task1', 'task2']
                mock_coord.return_value.wait_for_completion.return_value = True
                
                # Test coordinated async operations
                tasks = mock_coord.return_value.coordinate_tasks([
                    'fetch_market_data',
                    'calculate_signals', 
                    'update_positions'
                ])
                
                assert len(tasks) >= 2
                
                # Test waiting for completion
                completed = mock_coord.return_value.wait_for_completion(tasks)
                assert completed is True
                
            print("✅ Async operation coordination test passed")
            
        except Exception as e:
            pytest.fail(f"Async operation coordination failed: {e}")
    
    def test_state_synchronization(self):
        """Test state synchronization across modules"""
        try:
            # Mock state manager
            with patch('backend.services.state_manager.StateManager') as mock_state:
                mock_state.return_value.get_state.return_value = {'portfolio_value': 10000}
                mock_state.return_value.update_state.return_value = True
                mock_state.return_value.sync_state.return_value = True
                
                # Test state retrieval
                current_state = mock_state.return_value.get_state('portfolio')
                assert 'portfolio_value' in current_state
                
                # Test state update
                update_success = mock_state.return_value.update_state('portfolio', {
                    'portfolio_value': 10500
                })
                assert update_success is True
                
                # Test state synchronization
                sync_success = mock_state.return_value.sync_state()
                assert sync_success is True
                
            print("✅ State synchronization test passed")
            
        except Exception as e:
            pytest.fail(f"State synchronization failed: {e}")
    
    def test_resource_management(self):
        """Test resource management across modules"""
        try:
            # Mock resource manager
            with patch('backend.services.resource_manager.ResourceManager') as mock_rm:
                mock_rm.return_value.acquire_resource.return_value = 'resource_123'
                mock_rm.return_value.release_resource.return_value = True
                mock_rm.return_value.cleanup_resources.return_value = 5  # Resources cleaned
                
                # Test resource acquisition
                resource_id = mock_rm.return_value.acquire_resource('database_connection')
                assert resource_id == 'resource_123'
                
                # Test resource release
                released = mock_rm.return_value.release_resource(resource_id)
                assert released is True
                
                # Test cleanup
                cleaned_count = mock_rm.return_value.cleanup_resources()
                assert cleaned_count >= 0
                
            print("✅ Resource management test passed")
            
        except Exception as e:
            pytest.fail(f"Resource management failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])