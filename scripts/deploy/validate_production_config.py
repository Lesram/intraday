#!/usr/bin/env python3
"""
Pre-Deployment Configuration Validator

Validates all required environment variables and external service connectivity
before production deployment. Integrates with existing platform infrastructure:
- backend.infra.db for database connectivity
- backend.integrations.alpaca_* for broker API validation
- backend.infra.broker for Redis/message broker checks

Usage:
    python scripts/validate_production_config.py

Exit Codes:
    0 - All checks passed
    1 - One or more critical checks failed
    2 - Configuration errors (missing env vars, invalid values)
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple
import httpx

# Color codes for output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print formatted header."""
    print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^80}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.RESET}")

def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_info(text: str):
    """Print info message."""
    print(f"{Colors.WHITE}   {text}{Colors.RESET}")


class ConfigValidator:
    """Validates production configuration and connectivity."""
    
    def __init__(self):
        self.results: Dict[str, List[Tuple[str, bool, str]]] = {
            "environment_vars": [],
            "database": [],
            "broker_api": [],
            "message_broker": [],
            "platform_health": []
        }
        self.critical_failures = 0
        self.warnings = 0
    
    def check_env_var(self, var_name: str, required: bool = True, 
                     validate_fn=None, description: str = "") -> bool:
        """
        Check if environment variable exists and optionally validate its value.
        
        Args:
            var_name: Name of environment variable
            required: Whether variable is required for deployment
            validate_fn: Optional function to validate the value
            description: Description of what this var is for
        
        Returns:
            True if check passed, False otherwise
        """
        value = os.getenv(var_name)
        
        if value is None:
            if required:
                self.results["environment_vars"].append(
                    (var_name, False, f"MISSING (required): {description}")
                )
                self.critical_failures += 1
                return False
            else:
                self.results["environment_vars"].append(
                    (var_name, True, f"Optional (not set): {description}")
                )
                self.warnings += 1
                return True
        
        # Value exists, now validate if function provided
        if validate_fn:
            try:
                valid, msg = validate_fn(value)
                if not valid:
                    self.results["environment_vars"].append(
                        (var_name, False, f"INVALID: {msg}")
                    )
                    if required:
                        self.critical_failures += 1
                    else:
                        self.warnings += 1
                    return False
            except Exception as e:
                self.results["environment_vars"].append(
                    (var_name, False, f"VALIDATION ERROR: {str(e)}")
                )
                self.critical_failures += 1
                return False
        
        # Mask sensitive values in output
        if any(secret in var_name.lower() for secret in ['password', 'secret', 'key', 'token']):
            display_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
        else:
            display_value = value
        
        self.results["environment_vars"].append(
            (var_name, True, f"OK: {display_value}")
        )
        return True
    
    def validate_database_url(self, url: str) -> Tuple[bool, str]:
        """Validate DATABASE_URL format."""
        if not url:
            return False, "Empty URL"
        
        # Check for required components
        required_parts = ['postgresql', '://', '@', ':']
        for part in required_parts:
            if part not in url:
                return False, f"Missing required component: {part}"
        
        # Check for async driver
        if 'postgresql+asyncpg://' not in url and 'postgresql://' not in url:
            return False, "Must use postgresql:// or postgresql+asyncpg:// scheme"
        
        return True, "Valid PostgreSQL URL format"
    
    def validate_alpaca_key(self, key: str) -> Tuple[bool, str]:
        """Validate Alpaca API key format."""
        if not key:
            return False, "Empty key"
        
        # Alpaca keys typically start with PK (paper) or AK (live)
        if not (key.startswith('PK') or key.startswith('AK')):
            return False, "Invalid key format (should start with PK or AK)"
        
        if len(key) < 20:
            return False, "Key too short (likely invalid)"
        
        return True, "Valid Alpaca key format"
    
    async def check_database_connectivity(self) -> bool:
        """
        Check database connectivity using platform's existing infrastructure.
        Integrates with backend.infra.db module.
        """
        try:
            # Import platform's database module
            from backend.infra.db import init_db, db_health_check, get_db_session
            from sqlalchemy import text
            
            # Get DATABASE_URL
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                self.results["database"].append(
                    ("Connectivity", False, "DATABASE_URL not set")
                )
                self.critical_failures += 1
                return False
            
            # Initialize database connection using platform's init_db
            print_info("Initializing database connection...")
            try:
                engine, sessionmaker = init_db(db_url)
                print_info(f"Database engine created: {type(engine).__name__}")
            except Exception as e:
                self.results["database"].append(
                    ("Initialization", False, f"Failed to initialize: {str(e)}")
                )
                self.critical_failures += 1
                return False
            
            # Test health check using platform's health check function
            print_info("Running database health check...")
            healthy = await db_health_check()
            
            if not healthy:
                self.results["database"].append(
                    ("Health Check", False, "Health check returned False")
                )
                self.critical_failures += 1
                return False
            
            # Test actual query using platform's session
            print_info("Testing database query...")
            async for session in get_db_session():
                try:
                    result = await session.execute(text("SELECT 1 as test, version()"))
                    row = result.fetchone()
                    if row:
                        pg_version = row[1].split()[0] if len(row) > 1 else "unknown"
                        self.results["database"].append(
                            ("Connectivity", True, f"Connected to PostgreSQL {pg_version}")
                        )
                        self.results["database"].append(
                            ("Query Test", True, "SELECT query successful")
                        )
                    else:
                        self.results["database"].append(
                            ("Query Test", False, "Query returned no data")
                        )
                        self.critical_failures += 1
                        return False
                    
                    # Test users table exists (from our recent migration)
                    print_info("Verifying users table exists...")
                    result = await session.execute(text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = 'users'"
                    ))
                    count = result.scalar()
                    if count > 0:
                        self.results["database"].append(
                            ("Users Table", True, "Users table exists")
                        )
                    else:
                        self.results["database"].append(
                            ("Users Table", False, "Users table missing (run migration)")
                        )
                        self.warnings += 1
                    
                except Exception as e:
                    self.results["database"].append(
                        ("Query Test", False, f"Query failed: {str(e)}")
                    )
                    self.critical_failures += 1
                    return False
                
                break  # Exit after first session
            
            self.results["database"].append(
                ("Health Check", True, "All database checks passed")
            )
            return True
            
        except ImportError as e:
            self.results["database"].append(
                ("Import", False, f"Cannot import database module: {str(e)}")
            )
            self.critical_failures += 1
            return False
        except Exception as e:
            self.results["database"].append(
                ("Connectivity", False, f"Unexpected error: {str(e)}")
            )
            self.critical_failures += 1
            return False
    
    async def check_alpaca_api(self) -> bool:
        """
        Check Alpaca API connectivity and credentials.
        Integrates with existing platform's Alpaca integration.
        """
        api_key = os.getenv('ALPACA_API_KEY_ID')
        api_secret = os.getenv('ALPACA_SECRET_KEY')
        
        if not api_key or not api_secret:
            self.results["broker_api"].append(
                ("Credentials", False, "ALPACA_API_KEY_ID or ALPACA_SECRET_KEY missing")
            )
            self.critical_failures += 1
            return False
        
        # Determine base URL (paper vs live trading)
        if api_key.startswith('PK'):
            base_url = "https://paper-api.alpaca.markets"
            env_type = "Paper Trading"
        elif api_key.startswith('AK'):
            base_url = "https://api.alpaca.markets"
            env_type = "Live Trading"
        else:
            self.results["broker_api"].append(
                ("API Type", False, f"Unknown API key type: {api_key[:2]}")
            )
            self.critical_failures += 1
            return False
        
        self.results["broker_api"].append(
            ("API Type", True, f"{env_type} ({api_key[:2]}...{api_key[-4:]})")
        )
        
        # Test API connectivity
        print_info(f"Testing {env_type} API connectivity...")
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": api_secret
                }
                
                # Test account endpoint
                response = await client.get(
                    f"{base_url}/v2/account",
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    account = response.json()
                    account_status = account.get('status', 'unknown')
                    account_number = account.get('account_number', 'unknown')
                    
                    self.results["broker_api"].append(
                        ("Account API", True, f"Account {account_number[-4:]} ({account_status})")
                    )
                    
                    # Check account status
                    if account_status != 'ACTIVE':
                        self.results["broker_api"].append(
                            ("Account Status", False, f"Account not ACTIVE: {account_status}")
                        )
                        self.critical_failures += 1
                        return False
                    
                    # Get buying power to verify trading capabilities
                    buying_power = account.get('buying_power', '0')
                    self.results["broker_api"].append(
                        ("Buying Power", True, f"${float(buying_power):.2f} available")
                    )
                    
                elif response.status_code == 401:
                    self.results["broker_api"].append(
                        ("Account API", False, "Authentication failed (invalid credentials)")
                    )
                    self.critical_failures += 1
                    return False
                else:
                    self.results["broker_api"].append(
                        ("Account API", False, f"API returned {response.status_code}")
                    )
                    self.critical_failures += 1
                    return False
                
                # Test market data endpoint
                print_info("Testing market data API...")
                response = await client.get(
                    f"{base_url}/v2/stocks/AAPL/quotes/latest",
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    self.results["broker_api"].append(
                        ("Market Data API", True, "Market data accessible")
                    )
                else:
                    self.results["broker_api"].append(
                        ("Market Data API", False, f"Market data returned {response.status_code}")
                    )
                    self.warnings += 1
                
                return True
                
        except httpx.TimeoutException:
            self.results["broker_api"].append(
                ("Connectivity", False, "Request timeout (network issue?)")
            )
            self.critical_failures += 1
            return False
        except Exception as e:
            self.results["broker_api"].append(
                ("Connectivity", False, f"Connection failed: {str(e)}")
            )
            self.critical_failures += 1
            return False
    
    async def check_message_broker(self) -> bool:
        """
        Check message broker (Redis) connectivity.
        Integrates with platform's broker infrastructure.
        """
        try:
            from backend.infra.broker import broker_health_check
            
            print_info("Running message broker health check...")
            healthy = await broker_health_check()
            
            if healthy:
                self.results["message_broker"].append(
                    ("Redis Health", True, "Message broker healthy")
                )
                return True
            else:
                self.results["message_broker"].append(
                    ("Redis Health", False, "Message broker unhealthy")
                )
                # Not critical - platform can work without Redis
                self.warnings += 1
                return False
                
        except ImportError:
            self.results["message_broker"].append(
                ("Import", False, "Cannot import broker module")
            )
            self.warnings += 1
            return False
        except Exception as e:
            self.results["message_broker"].append(
                ("Health Check", False, f"Check failed: {str(e)}")
            )
            self.warnings += 1
            return False
    
    async def check_platform_health(self) -> bool:
        """
        Check if platform is running and healthy.
        Tests actual deployed instance.
        """
        # Try to determine platform URL from environment
        platform_url = os.getenv('PLATFORM_URL', 'http://localhost:8000')
        
        print_info(f"Checking platform health at {platform_url}...")
        
        try:
            async with httpx.AsyncClient() as client:
                # Test health endpoint
                response = await client.get(
                    f"{platform_url}/health",
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    self.results["platform_health"].append(
                        ("/health", True, "Health endpoint responding")
                    )
                    
                    # Try to parse health response
                    try:
                        health_data = response.json()
                        status = health_data.get('status', 'unknown')
                        if status == 'healthy':
                            self.results["platform_health"].append(
                                ("Status", True, "Platform reports healthy")
                            )
                        else:
                            self.results["platform_health"].append(
                                ("Status", False, f"Platform status: {status}")
                            )
                            self.warnings += 1
                    except:
                        pass
                    
                    return True
                else:
                    self.results["platform_health"].append(
                        ("/health", False, f"Health endpoint returned {response.status_code}")
                    )
                    self.warnings += 1
                    return False
                    
        except httpx.ConnectError:
            self.results["platform_health"].append(
                ("Platform", False, f"Cannot connect to {platform_url} (not running?)")
            )
            # Not critical if this is pre-deployment validation
            self.warnings += 1
            return False
        except Exception as e:
            self.results["platform_health"].append(
                ("Platform", False, f"Health check failed: {str(e)}")
            )
            self.warnings += 1
            return False
    
    def print_results(self):
        """Print formatted results."""
        print_header("VALIDATION RESULTS")
        
        # Print each category
        for category, checks in self.results.items():
            if not checks:
                continue
            
            print(f"\n{Colors.BOLD}{Colors.CYAN}{category.replace('_', ' ').title()}:{Colors.RESET}")
            for name, passed, message in checks:
                if passed:
                    print_success(f"{name}: {message}")
                else:
                    print_error(f"{name}: {message}")
        
        # Print summary
        print_header("SUMMARY")
        
        total_checks = sum(len(checks) for checks in self.results.values())
        passed_checks = sum(1 for checks in self.results.values() for _, passed, _ in checks if passed)
        
        print(f"{Colors.WHITE}Total Checks: {total_checks}{Colors.RESET}")
        print(f"{Colors.GREEN}Passed: {passed_checks}{Colors.RESET}")
        print(f"{Colors.RED}Failed: {total_checks - passed_checks}{Colors.RESET}")
        print(f"{Colors.RED}Critical Failures: {self.critical_failures}{Colors.RESET}")
        print(f"{Colors.YELLOW}Warnings: {self.warnings}{Colors.RESET}")
        
        if self.critical_failures == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ VALIDATION PASSED - Ready for deployment{Colors.RESET}\n")
            return 0
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ VALIDATION FAILED - Fix critical issues before deployment{Colors.RESET}\n")
            return 1


async def main():
    """Main validation function."""
    print_header("PRE-DEPLOYMENT CONFIGURATION VALIDATOR")
    print(f"{Colors.WHITE}Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
    print(f"{Colors.WHITE}Platform: Algorithmic Trading Platform{Colors.RESET}\n")
    
    validator = ConfigValidator()
    
    # ============================================================================
    # STEP 1: Environment Variables
    # ============================================================================
    print_header("STEP 1: Environment Variables")
    
    # Critical database variables
    validator.check_env_var(
        "DATABASE_URL", 
        required=True,
        validate_fn=validator.validate_database_url,
        description="PostgreSQL connection string"
    )
    
    # Critical Alpaca API variables
    validator.check_env_var(
        "ALPACA_API_KEY_ID",
        required=True,
        validate_fn=validator.validate_alpaca_key,
        description="Alpaca API key (paper or live trading)"
    )
    
    validator.check_env_var(
        "ALPACA_SECRET_KEY",
        required=True,
        description="Alpaca API secret key"
    )
    
    # Optional but recommended variables
    validator.check_env_var(
        "JWT_SECRET_KEY",
        required=False,
        description="JWT signing secret (uses default if not set)"
    )
    
    validator.check_env_var(
        "REDIS_URL",
        required=False,
        description="Redis connection string (optional message broker)"
    )
    
    validator.check_env_var(
        "LOG_LEVEL",
        required=False,
        description="Logging level (default: INFO)"
    )
    
    validator.check_env_var(
        "PLATFORM_URL",
        required=False,
        description="Platform URL for health checks (default: http://localhost:8000)"
    )
    
    # ============================================================================
    # STEP 2: Database Connectivity
    # ============================================================================
    print_header("STEP 2: Database Connectivity")
    
    await validator.check_database_connectivity()
    
    # ============================================================================
    # STEP 3: Broker API Connectivity
    # ============================================================================
    print_header("STEP 3: Broker API Connectivity")
    
    await validator.check_alpaca_api()
    
    # ============================================================================
    # STEP 4: Message Broker (Optional)
    # ============================================================================
    print_header("STEP 4: Message Broker (Optional)")
    
    await validator.check_message_broker()
    
    # ============================================================================
    # STEP 5: Platform Health (Optional)
    # ============================================================================
    print_header("STEP 5: Platform Health Check (Optional)")
    
    await validator.check_platform_health()
    
    # ============================================================================
    # Print Results
    # ============================================================================
    exit_code = validator.print_results()
    
    return exit_code


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Validation interrupted by user{Colors.RESET}\n")
        sys.exit(2)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {str(e)}{Colors.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(2)
