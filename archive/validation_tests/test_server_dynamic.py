"""
Updated Test Server with Dynamic Port Management
Avoids port conflicts by using dynamic port allocation
"""

import asyncio
import logging
from typing import Optional

try:
    import uvicorn
    from fastapi import FastAPI
except ImportError:
    print("FastAPI and uvicorn required for test server. Install with: pip install fastapi uvicorn")
    exit(1)

from backend.utils.port_management import port_manager, get_free_port, get_port_info, kill_port_process

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_app() -> FastAPI:
    """Create a simple FastAPI app for testing."""
    app = FastAPI(title="Dynamic Test Server", version="1.0.0")
    
    @app.get("/")
    async def root():
        return {"message": "Test server running", "status": "healthy"}
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "server": "test"}
    
    @app.get("/port-info")
    async def port_info():
        return {"message": "Port management working correctly"}
    
    return app


def resolve_port_conflict(preferred_port: int = 8001) -> int:
    """
    Resolve port conflicts by either freeing the port or finding an alternative.
    
    Args:
        preferred_port: The port we'd like to use
        
    Returns:
        An available port number
    """
    print(f"\n🔍 Checking port {preferred_port} availability...")
    
    port_info = get_port_info(preferred_port)
    print(f"Port {preferred_port} info: {port_info}")
    
    if port_info["available"]:
        print(f"✅ Port {preferred_port} is available")
        return preferred_port
    
    print(f"⚠️  Port {preferred_port} is in use")
    
    if port_info["process_info"]:
        proc_info = port_info["process_info"]
        print(f"   Process: {proc_info['name']} (PID: {proc_info['pid']})")
        
        # Ask user what to do
        print(f"\nOptions:")
        print(f"1. Kill the process using port {preferred_port}")
        print(f"2. Use a different port automatically")
        
        choice = input("Enter choice (1 or 2, default=2): ").strip()
        
        if choice == "1":
            print(f"🔄 Attempting to kill process {proc_info['pid']}...")
            if kill_port_process(preferred_port):
                print(f"✅ Successfully freed port {preferred_port}")
                return preferred_port
            else:
                print(f"❌ Failed to kill process, finding alternative port...")
        else:
            print(f"🔄 Finding alternative port...")
    
    # Find alternative port
    alternative_port = get_free_port(preferred_port + 1)
    print(f"✅ Found alternative port: {alternative_port}")
    return alternative_port


async def start_server_async(app: FastAPI, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    """Start the server asynchronously with dynamic port management."""
    
    if port is None:
        port = resolve_port_conflict(8001)
    else:
        port = resolve_port_conflict(port)
    
    print(f"🚀 Starting server on http://{host}:{port}...")
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        print(f"\n🛑 Server shutdown requested")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        print(f"🔄 Releasing port {port}")
        port_manager.release_port(port)


def start_server_sync(app: FastAPI, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    """Start the server synchronously with dynamic port management."""
    
    if port is None:
        port = resolve_port_conflict(8001)
    else:
        port = resolve_port_conflict(port)
    
    print(f"🚀 Starting server on http://{host}:{port}...")
    
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print(f"\n🛑 Server shutdown requested")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        print(f"🔄 Releasing port {port}")
        port_manager.release_port(port)


def main():
    """Main entry point for the test server."""
    print("=" * 60)
    print("DYNAMIC PORT TEST SERVER")
    print("=" * 60)
    
    app = create_test_app()
    
    # Check for command line arguments
    import sys
    
    port = None
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            print(f"Using specified port: {port}")
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            return
    
    # Check if we should run async or sync
    run_async = "--async" in sys.argv
    
    if run_async:
        print("Running in async mode...")
        asyncio.run(start_server_async(app, port=port))
    else:
        print("Running in sync mode...")
        start_server_sync(app, port=port)


def test_port_management():
    """Test the port management functionality."""
    print("\n" + "=" * 60)
    print("PORT MANAGEMENT TEST")
    print("=" * 60)
    
    # Test port availability checks
    print("\n🔍 Testing port availability checks...")
    
    test_ports = [8001, 8002, 8003, 8080, 3000]
    for port in test_ports:
        available = port_manager.is_port_available(port)
        status = "✅ Available" if available else "❌ In use"
        print(f"  Port {port}: {status}")
        
        if not available:
            info = get_port_info(port)
            if info.get("process_info"):
                proc = info["process_info"]
                print(f"    → Process: {proc['name']} (PID: {proc['pid']})")
    
    # Test dynamic allocation
    print(f"\n🔍 Testing dynamic port allocation...")
    
    allocated_ports = []
    for i in range(5):
        try:
            port = get_free_port(8001 + i)
            allocated_ports.append(port)
            print(f"  Allocated port: {port}")
        except Exception as e:
            print(f"  ❌ Failed to allocate port: {e}")
    
    # Release allocated ports
    print(f"\n🔄 Releasing allocated ports...")
    for port in allocated_ports:
        port_manager.release_port(port)
        print(f"  Released port: {port}")
    
    print(f"\n✅ Port management test completed")


if __name__ == "__main__":
    import sys
    
    if "--test" in sys.argv:
        test_port_management()
    else:
        main()