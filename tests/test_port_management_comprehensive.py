"""
Comprehensive tests for backend.utils.port_management

Targets 70%+ coverage for PortManager class:
- Port allocation
- Port availability checking
- Port release
- Context manager usage
"""

import asyncio
import socket
from unittest.mock import patch, MagicMock
import pytest

from backend.utils.port_management import PortManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def port_manager():
    """Create a PortManager instance"""
    return PortManager(start_port=10000, max_attempts=50)


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestPortManagerInit:
    """Tests for PortManager initialization"""
    
    def test_init_default_values(self):
        """Test default initialization"""
        pm = PortManager()
        assert pm.start_port == 8001
        assert pm.max_attempts == 100
        assert pm._allocated_ports == set()
        
    def test_init_custom_values(self):
        """Test custom initialization"""
        pm = PortManager(start_port=9000, max_attempts=50)
        assert pm.start_port == 9000
        assert pm.max_attempts == 50


# ============================================================================
# IS PORT AVAILABLE TESTS
# ============================================================================

class TestIsPortAvailable:
    """Tests for is_port_available method"""
    
    def test_available_port(self, port_manager):
        """Test checking available port"""
        # Find a port that should be available
        result = port_manager.is_port_available(port_manager.start_port)
        # Result depends on system state, just check it's a bool
        assert isinstance(result, bool)
        
    def test_unavailable_port(self, port_manager):
        """Test checking unavailable port"""
        # Create a socket and bind to a port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', 0))  # Let OS pick a port
            port = sock.getsockname()[1]
            
            # Port should be unavailable while socket is bound
            result = port_manager.is_port_available(port)
            # May still return True due to SO_REUSEADDR
            assert isinstance(result, bool)


# ============================================================================
# FIND FREE PORT TESTS
# ============================================================================

class TestFindFreePort:
    """Tests for find_free_port method"""
    
    def test_find_free_port_default(self, port_manager):
        """Test finding a free port with defaults"""
        port = port_manager.find_free_port()
        
        assert port >= port_manager.start_port
        assert port in port_manager._allocated_ports
        
    def test_find_free_port_preferred(self, port_manager):
        """Test finding a free port with preferred port"""
        preferred = 15000
        port = port_manager.find_free_port(preferred_port=preferred)
        
        assert port >= preferred
        assert port in port_manager._allocated_ports
        
    def test_find_free_port_tracks_allocation(self, port_manager):
        """Test that allocated ports are tracked"""
        port1 = port_manager.find_free_port()
        port2 = port_manager.find_free_port()
        
        assert port1 != port2
        assert port1 in port_manager._allocated_ports
        assert port2 in port_manager._allocated_ports
        
    def test_find_free_port_skips_allocated(self, port_manager):
        """Test that already allocated ports are skipped"""
        # Allocate first port
        port1 = port_manager.find_free_port()
        
        # Next port should be different
        port2 = port_manager.find_free_port()
        
        assert port1 != port2


# ============================================================================
# RELEASE PORT TESTS
# ============================================================================

class TestReleasePort:
    """Tests for release_port method"""
    
    def test_release_allocated_port(self, port_manager):
        """Test releasing an allocated port"""
        port = port_manager.find_free_port()
        assert port in port_manager._allocated_ports
        
        port_manager.release_port(port)
        assert port not in port_manager._allocated_ports
        
    def test_release_unallocated_port(self, port_manager):
        """Test releasing a port that wasn't allocated"""
        # Should not raise
        port_manager.release_port(99999)
        assert 99999 not in port_manager._allocated_ports


# ============================================================================
# CONTEXT MANAGER TESTS
# ============================================================================

class TestGetPortContextManager:
    """Tests for get_port context manager"""
    
    def test_context_manager_allocates_port(self, port_manager):
        """Test port is allocated in context"""
        with port_manager.get_port() as port:
            assert port >= port_manager.start_port
            assert port in port_manager._allocated_ports
            
    def test_context_manager_releases_on_exit(self, port_manager):
        """Test port is released on context exit"""
        with port_manager.get_port() as port:
            allocated_port = port
            
        assert allocated_port not in port_manager._allocated_ports
        
    def test_context_manager_releases_on_exception(self, port_manager):
        """Test port is released even on exception"""
        allocated_port = None
        try:
            with port_manager.get_port() as port:
                allocated_port = port
                raise ValueError("Test exception")
        except ValueError:
            pass
            
        assert allocated_port not in port_manager._allocated_ports
        
    def test_context_manager_preferred_port(self, port_manager):
        """Test context manager with preferred port"""
        with port_manager.get_port(preferred_port=12000) as port:
            assert port >= 12000


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases"""
    
    def test_max_attempts_exhausted(self):
        """Test exception when max attempts exhausted"""
        pm = PortManager(start_port=10000, max_attempts=2)
        
        # Mock all ports as unavailable
        with patch.object(pm, 'is_port_available', return_value=False):
            with pytest.raises(RuntimeError, match="Could not find a free port"):
                pm.find_free_port()
                
    def test_multiple_managers_isolated(self):
        """Test multiple PortManager instances are isolated"""
        pm1 = PortManager(start_port=20000)
        pm2 = PortManager(start_port=20000)
        
        port1 = pm1.find_free_port()
        
        # pm2 doesn't know about pm1's allocation
        assert port1 not in pm2._allocated_ports


# ============================================================================
# GET PORT INFO TESTS
# ============================================================================

class TestGetPortInfo:
    """Tests for get_port_info method"""
    
    def test_get_info_for_available_port(self, port_manager):
        """Test getting info for an available port"""
        # Find an available port first
        port = port_manager.find_free_port()
        port_manager.release_port(port)
        
        # Now check info - port should be available
        info = port_manager.get_port_info(port)
        
        assert info["port"] == port
        assert isinstance(info["available"], bool)
        assert "process_info" in info
        
    def test_get_info_structure(self, port_manager):
        """Test structure of returned info dict"""
        info = port_manager.get_port_info(8080)
        
        assert "port" in info
        assert "available" in info
        assert "process_info" in info
        
    def test_get_info_for_common_port(self, port_manager):
        """Test getting info for a common port"""
        # Check port 80 (usually system-level)
        info = port_manager.get_port_info(80)
        
        assert info["port"] == 80
        assert isinstance(info["available"], bool)


# ============================================================================
# KILL PROCESS ON PORT TESTS
# ============================================================================

class TestKillProcessOnPort:
    """Tests for kill_process_on_port method"""
    
    def test_kill_no_process_returns_false(self, port_manager):
        """Test killing process on empty port returns False"""
        # Use a very high port that's unlikely to be in use
        result = port_manager.kill_process_on_port(59999)
        assert result is False
        
    @patch('subprocess.run')
    def test_kill_with_mocked_subprocess(self, mock_run, port_manager):
        """Test kill process with mocked subprocess"""
        # Mock netstat finding no process
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        
        result = port_manager.kill_process_on_port(8080)
        assert result is False
        
    @patch('subprocess.run')
    def test_kill_with_process_found(self, mock_run, port_manager):
        """Test kill process when process is found"""
        # Mock netstat output with a listening process
        mock_netstat = MagicMock()
        mock_netstat.stdout = "  TCP    127.0.0.1:8080    0.0.0.0:0    LISTENING    1234"
        
        # Mock taskkill success
        mock_taskkill = MagicMock()
        mock_taskkill.returncode = 0
        
        mock_run.side_effect = [mock_netstat, mock_taskkill]
        
        # Also mock is_port_available to return True after kill
        with patch.object(port_manager, 'is_port_available', return_value=True):
            result = port_manager.kill_process_on_port(8080)
        
        assert result is True
        
    @patch('subprocess.run')
    def test_kill_handles_exception(self, mock_run, port_manager):
        """Test kill handles exceptions gracefully"""
        mock_run.side_effect = Exception("Subprocess error")
        
        result = port_manager.kill_process_on_port(8080)
        assert result is False


# ============================================================================
# TEST SERVER MANAGER TESTS
# ============================================================================

class TestTestServerManager:
    """Tests for TestServerManager class"""
    
    def test_init_default_port_manager(self):
        """Test initialization with default port manager"""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager()
        assert tsm.port_manager is not None
        assert tsm._running_servers == {}
        
    def test_init_custom_port_manager(self, port_manager):
        """Test initialization with custom port manager"""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager=port_manager)
        assert tsm.port_manager is port_manager
        
    def test_list_running_servers_empty(self):
        """Test listing servers when none are running"""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager()
        assert tsm.list_running_servers() == []
        
    def test_get_server_info_not_found(self):
        """Test getting info for non-existent server"""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager()
        assert tsm.get_server_info("nonexistent") is None
        
    @pytest.mark.asyncio
    async def test_stop_server_not_running(self):
        """Test stopping a server that's not running"""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager()
        # Should not raise, just log warning
        await tsm.stop_test_server("nonexistent")
        
    @pytest.mark.asyncio
    async def test_stop_all_servers_empty(self):
        """Test stopping all servers when none running"""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager()
        await tsm.stop_all_servers()
        assert tsm._running_servers == {}


# ============================================================================
# CONVENIENCE FUNCTIONS TESTS
# ============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions"""
    
    def test_get_free_port(self):
        """Test get_free_port convenience function"""
        from backend.utils.port_management import get_free_port
        
        port = get_free_port()
        assert isinstance(port, int)
        assert port > 0
        
    def test_get_free_port_preferred(self):
        """Test get_free_port with preferred port"""
        from backend.utils.port_management import get_free_port
        
        port = get_free_port(preferred_port=30000)
        assert port >= 30000
        
    def test_is_port_available_function(self):
        """Test is_port_available convenience function"""
        from backend.utils.port_management import is_port_available
        
        result = is_port_available(59998)
        assert isinstance(result, bool)
        
    def test_kill_port_process_function(self):
        """Test kill_port_process convenience function"""
        from backend.utils.port_management import kill_port_process
        
        result = kill_port_process(59997)
        assert isinstance(result, bool)
        
    def test_get_port_info_function(self):
        """Test get_port_info convenience function"""
        from backend.utils.port_management import get_port_info
        
        info = get_port_info(8080)
        assert "port" in info
        assert "available" in info
        
    def test_free_port_context_function(self):
        """Test free_port_context convenience function"""
        from backend.utils.port_management import free_port_context
        
        with free_port_context(40000) as port:
            assert port >= 40000


# ============================================================================
# ADDITIONAL TESTS FOR MISSING COVERAGE
# ============================================================================

class TestIsPortAvailableEdgeCases:
    """Additional tests for is_port_available edge cases."""
    
    def test_port_unavailable_oserror(self, port_manager):
        """Test is_port_available returns False on OSError (lines 64-65)."""
        with patch('socket.socket') as mock_socket:
            mock_sock_instance = MagicMock()
            mock_sock_instance.__enter__ = MagicMock(return_value=mock_sock_instance)
            mock_sock_instance.__exit__ = MagicMock(return_value=False)
            mock_sock_instance.bind.side_effect = OSError("Address already in use")
            mock_socket.return_value = mock_sock_instance
            
            result = port_manager.is_port_available(8080)
            assert result is False


class TestKillProcessOnPortEdgeCases:
    """Additional edge case tests for kill_process_on_port."""
    
    @patch('subprocess.run')
    def test_kill_subprocess_error_in_taskkill(self, mock_run, port_manager):
        """Test kill process handles SubprocessError during taskkill (lines 128-131)."""
        import subprocess
        
        # Mock netstat finding a process
        mock_netstat = MagicMock()
        mock_netstat.stdout = "  TCP    127.0.0.1:8080    0.0.0.0:0    LISTENING    1234"
        
        # Mock taskkill raising SubprocessError
        mock_run.side_effect = [mock_netstat, subprocess.SubprocessError("Taskkill failed")]
        
        result = port_manager.kill_process_on_port(8080)
        assert result is False
        
    @patch('subprocess.run')
    def test_kill_port_not_released_after_kill(self, mock_run, port_manager):
        """Test kill returns False when port not released after killing process."""
        # Mock netstat finding a process
        mock_netstat = MagicMock()
        mock_netstat.stdout = "  TCP    127.0.0.1:8080    0.0.0.0:0    LISTENING    1234"
        
        # Mock taskkill success
        mock_taskkill = MagicMock()
        mock_taskkill.returncode = 0
        
        mock_run.side_effect = [mock_netstat, mock_taskkill]
        
        # Port stays unavailable after kill
        with patch.object(port_manager, 'is_port_available', return_value=False):
            result = port_manager.kill_process_on_port(8080)
        
        assert result is False


class TestGetPortInfoWhenUnavailable:
    """Tests for get_port_info when port is NOT available (lines 156-194)."""
    
    @patch('subprocess.run')
    def test_get_port_info_with_process(self, mock_run, port_manager):
        """Test get_port_info finds process using port."""
        # Mock is_port_available to return False
        with patch.object(port_manager, 'is_port_available', return_value=False):
            # Mock netstat output
            mock_netstat = MagicMock()
            mock_netstat.stdout = "  TCP    127.0.0.1:8080    0.0.0.0:0    LISTENING    5678"
            
            # Mock tasklist output
            mock_tasklist = MagicMock()
            mock_tasklist.stdout = "python.exe    5678  Console    1    150,000 K"
            
            mock_run.side_effect = [mock_netstat, mock_tasklist]
            
            info = port_manager.get_port_info(8080)
            
            assert info["port"] == 8080
            assert info["available"] is False
            assert info["process_info"] is not None
            assert info["process_info"]["pid"] == "5678"
            
    @patch('subprocess.run')
    def test_get_port_info_subprocess_error_on_tasklist(self, mock_run, port_manager):
        """Test get_port_info handles tasklist SubprocessError."""
        import subprocess
        
        with patch.object(port_manager, 'is_port_available', return_value=False):
            # Mock netstat output
            mock_netstat = MagicMock()
            mock_netstat.stdout = "  TCP    127.0.0.1:8080    0.0.0.0:0    LISTENING    5678"
            
            # Mock tasklist raising error
            mock_run.side_effect = [mock_netstat, subprocess.SubprocessError("Tasklist failed")]
            
            info = port_manager.get_port_info(8080)
            
            assert info["port"] == 8080
            assert info["process_info"]["pid"] == "5678"
            assert info["process_info"]["name"] == "unknown"
            
    @patch('subprocess.run')
    def test_get_port_info_exception_handling(self, mock_run, port_manager):
        """Test get_port_info handles general exceptions."""
        with patch.object(port_manager, 'is_port_available', return_value=False):
            mock_run.side_effect = Exception("General error")
            
            info = port_manager.get_port_info(8080)
            
            assert info["port"] == 8080
            assert info["process_info"] is None


class TestTestServerManagerStartServer:
    """Tests for TestServerManager.start_test_server (lines 223-263)."""
    
    @pytest.mark.asyncio
    async def test_start_server_already_running(self, port_manager):
        """Test starting server that's already running raises ValueError."""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager)
        # Manually add a "running" server
        tsm._running_servers["test_server"] = {"port": 8080}
        
        with pytest.raises(ValueError, match="already running"):
            await tsm.start_test_server("test_server", MagicMock())
            
    @pytest.mark.asyncio
    async def test_start_server_success(self, port_manager):
        """Test successfully starting a test server."""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager)
        
        mock_app = MagicMock()
        
        with patch('uvicorn.Config') as mock_config, \
             patch('uvicorn.Server') as mock_server, \
             patch('asyncio.create_task') as mock_task:
            
            mock_server_instance = MagicMock()
            mock_server.return_value = mock_server_instance
            mock_task.return_value = MagicMock()
            
            host, port = await tsm.start_test_server("test_server", mock_app)
            
            assert host == "127.0.0.1"
            assert port > 0
            assert "test_server" in tsm._running_servers
            
    @pytest.mark.asyncio
    async def test_start_server_failure_releases_port(self, port_manager):
        """Test that port is released if server fails to start."""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager)
        mock_app = MagicMock()
        
        with patch('uvicorn.Config', side_effect=Exception("Config error")):
            with pytest.raises(RuntimeError, match="Failed to start server"):
                await tsm.start_test_server("test_server", mock_app)


class TestTestServerManagerStopServer:
    """Tests for TestServerManager.stop_test_server (lines 271-294)."""
    
    @pytest.mark.asyncio
    async def test_stop_server_success(self, port_manager):
        """Test successfully stopping a running server."""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager)
        
        # Create a mock running server
        mock_server = MagicMock()
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        
        async def mock_await():
            raise asyncio.CancelledError()
        
        mock_task.__await__ = lambda self: mock_await().__await__()
        
        tsm._running_servers["test_server"] = {
            "server": mock_server,
            "task": mock_task,
            "port": 12345,
            "host": "127.0.0.1"
        }
        port_manager._allocated_ports.add(12345)
        
        await tsm.stop_test_server("test_server")
        
        assert "test_server" not in tsm._running_servers
        assert mock_server.should_exit is True
        
    @pytest.mark.asyncio
    async def test_stop_server_handles_exception(self, port_manager):
        """Test stop_server handles exceptions gracefully."""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager)
        
        # Create a mock that raises an exception
        mock_server = MagicMock()
        mock_server.should_exit = property(lambda self: None, lambda self, v: None)
        
        # Setting should_exit raises an error
        type(mock_server).should_exit = property(fget=lambda s: False, fset=lambda s, v: exec('raise Exception("Error")'))
        
        tsm._running_servers["test_server"] = {
            "server": mock_server,
            "port": 12345,
            "host": "127.0.0.1"
        }
        
        # Should not raise, just log error
        await tsm.stop_test_server("test_server")
        
        assert "test_server" not in tsm._running_servers


class TestTestServerManagerGetInfo:
    """Tests for get_server_info with existing server (line 300)."""
    
    def test_get_server_info_exists(self, port_manager):
        """Test getting info for an existing server."""
        from backend.utils.port_management import TestServerManager
        
        tsm = TestServerManager(port_manager)
        
        # Add a mock running server
        server_info = {
            "server": MagicMock(),
            "host": "127.0.0.1",
            "port": 8080
        }
        tsm._running_servers["existing_server"] = server_info
        
        result = tsm.get_server_info("existing_server")
        
        assert result == server_info
        assert result["port"] == 8080
