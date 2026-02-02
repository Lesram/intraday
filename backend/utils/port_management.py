"""
Port Management Solution for Health Check Tests
Implements dynamic port allocation to avoid conflicts
"""

import asyncio
from contextlib import contextmanager
import logging
import socket
import time

logger = logging.getLogger(__name__)


class PortManager:
    """Manages port allocation and conflict resolution for test environments."""

    def __init__(self, start_port: int = 8001, max_attempts: int = 100):
        self.start_port = start_port
        self.max_attempts = max_attempts
        self._allocated_ports = set()

    def find_free_port(self, preferred_port: int | None = None) -> int:
        """
        Find a free port, optionally starting from a preferred port.

        Args:
            preferred_port: Port to try first, defaults to start_port

        Returns:
            Available port number

        Raises:
            RuntimeError: If no free port found within max_attempts
        """
        if preferred_port is None:
            preferred_port = self.start_port

        for attempt in range(self.max_attempts):
            port = preferred_port + attempt
            if self.is_port_available(port) and port not in self._allocated_ports:
                self._allocated_ports.add(port)
                logger.info(f"Allocated port {port} (attempt {attempt + 1})")
                return port

        raise RuntimeError(f"Could not find a free port after {self.max_attempts} attempts starting from {preferred_port}")

    def is_port_available(self, port: int, host: str = "127.0.0.1") -> bool:
        """
        Check if a port is available for binding.

        Args:
            port: Port number to check
            host: Host address to check

        Returns:
            True if port is available, False otherwise
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                return True
        except OSError:
            return False

    def release_port(self, port: int) -> None:
        """Release a previously allocated port."""
        self._allocated_ports.discard(port)
        logger.info(f"Released port {port}")

    @contextmanager
    def get_port(self, preferred_port: int | None = None):
        """
        Context manager to get and automatically release a port.

        Args:
            preferred_port: Preferred port number

        Yields:
            Available port number
        """
        port = self.find_free_port(preferred_port)
        try:
            yield port
        finally:
            self.release_port(port)

    def kill_process_on_port(self, port: int) -> bool:
        """
        Kill any process currently using the specified port.

        Args:
            port: Port number to free up

        Returns:
            True if process was killed, False if no process found
        """
        try:
            import subprocess

            # Find process using the port on Windows
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.split('\n'):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            # Kill the process
                            subprocess.run(
                                ["taskkill", "/PID", pid, "/F"],
                                capture_output=True,
                                timeout=5
                            )
                            logger.info(f"Killed process {pid} using port {port}")

                            # Wait for port to be released
                            for _ in range(10):
                                if self.is_port_available(port):
                                    return True
                                time.sleep(0.5)

                        except subprocess.SubprocessError as e:
                            logger.error(f"Failed to kill process {pid}: {e}")

            return False

        except Exception as e:
            logger.error(f"Failed to kill process on port {port}: {e}")
            return False

    def get_port_info(self, port: int) -> dict:
        """
        Get information about what's using a specific port.

        Args:
            port: Port number to check

        Returns:
            Dictionary with port usage information
        """
        info = {
            "port": port,
            "available": self.is_port_available(port),
            "process_info": None
        }

        if not info["available"]:
            try:
                import subprocess
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                for line in result.stdout.split('\n'):
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = parts[-1]

                            # Get process name
                            try:
                                proc_result = subprocess.run(
                                    ["tasklist", "/FI", f"PID eq {pid}"],
                                    capture_output=True,
                                    text=True,
                                    timeout=5
                                )

                                for proc_line in proc_result.stdout.split('\n'):
                                    if pid in proc_line:
                                        proc_parts = proc_line.split()
                                        if len(proc_parts) >= 2:
                                            info["process_info"] = {
                                                "pid": pid,
                                                "name": proc_parts[0]
                                            }
                                        break
                            except subprocess.SubprocessError:
                                info["process_info"] = {"pid": pid, "name": "unknown"}
                            break

            except Exception as e:
                logger.error(f"Failed to get port info for {port}: {e}")

        return info


class TestServerManager:
    """Manages test servers with dynamic port allocation."""

    def __init__(self, port_manager: PortManager | None = None):
        self.port_manager = port_manager or PortManager()
        self._running_servers = {}

    async def start_test_server(self,
                               server_name: str,
                               app,
                               preferred_port: int | None = None,
                               host: str = "127.0.0.1") -> tuple[str, int]:
        """
        Start a test server on an available port.

        Args:
            server_name: Unique identifier for the server
            app: FastAPI or similar app instance
            preferred_port: Preferred port number
            host: Host address

        Returns:
            Tuple of (host, port) for the running server
        """
        if server_name in self._running_servers:
            raise ValueError(f"Server {server_name} is already running")

        port = self.port_manager.find_free_port(preferred_port)

        try:
            import uvicorn

            # Create server config
            config = uvicorn.Config(
                app=app,
                host=host,
                port=port,
                log_level="error",  # Reduce noise in tests
                access_log=False
            )

            # Start server in background
            server = uvicorn.Server(config)

            # Store server info
            self._running_servers[server_name] = {
                "server": server,
                "host": host,
                "port": port,
                "config": config
            }

            # Start server asynchronously
            task = asyncio.create_task(server.serve())
            self._running_servers[server_name]["task"] = task

            # Wait for server to start
            await asyncio.sleep(0.5)

            logger.info(f"Test server '{server_name}' started on {host}:{port}")
            return host, port

        except Exception as e:
            self.port_manager.release_port(port)
            raise RuntimeError(f"Failed to start server {server_name}: {e}")

    async def stop_test_server(self, server_name: str) -> None:
        """Stop a running test server."""
        if server_name not in self._running_servers:
            logger.warning(f"Server {server_name} is not running")
            return

        server_info = self._running_servers[server_name]

        try:
            # Stop the server
            server_info["server"].should_exit = True

            # Cancel the task
            if "task" in server_info:
                server_info["task"].cancel()
                try:
                    await server_info["task"]
                except asyncio.CancelledError:
                    pass

            # Release the port
            self.port_manager.release_port(server_info["port"])

            logger.info(f"Test server '{server_name}' stopped")

        except Exception as e:
            logger.error(f"Error stopping server {server_name}: {e}")

        finally:
            del self._running_servers[server_name]

    async def stop_all_servers(self) -> None:
        """Stop all running test servers."""
        server_names = list(self._running_servers.keys())
        for server_name in server_names:
            await self.stop_test_server(server_name)

    def get_server_info(self, server_name: str) -> dict | None:
        """Get information about a running server."""
        return self._running_servers.get(server_name)

    def list_running_servers(self) -> list:
        """Get list of all running server names."""
        return list(self._running_servers.keys())


# Global instances
port_manager = PortManager()
test_server_manager = TestServerManager(port_manager)


# Convenience functions
def get_free_port(preferred_port: int | None = None) -> int:
    """Get a free port for testing."""
    return port_manager.find_free_port(preferred_port)


def is_port_available(port: int) -> bool:
    """Check if a port is available."""
    return port_manager.is_port_available(port)


def kill_port_process(port: int) -> bool:
    """Kill process using a specific port."""
    return port_manager.kill_process_on_port(port)


def get_port_info(port: int) -> dict:
    """Get information about port usage."""
    return port_manager.get_port_info(port)


@contextmanager
def free_port_context(preferred_port: int | None = None):
    """Context manager for temporary port allocation."""
    with port_manager.get_port(preferred_port) as port:
        yield port
