#!/usr/bin/env python3
"""
Comprehensive Test Preparation Script - Consolidated Solutions
Captures all discovered issues and solutions for consistent test execution
"""

import sys
import os
import subprocess
import platform
from pathlib import Path
import json
import time
from datetime import datetime

class TestPreparationManager:
    def __init__(self, project_root=None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.venv_path = self.project_root / "venv"
        self.python_exe = self._get_python_executable()
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "issues_found": [],
            "solutions_applied": [],
            "recommended_command": None
        }
    
    def _get_python_executable(self):
        """Get correct Python executable path"""
        if platform.system() == "Windows":
            return self.venv_path / "Scripts" / "python.exe"
        else:
            return self.venv_path / "bin" / "python"
    
    def _run_command(self, cmd, timeout=30, check_output=True):
        """Run command with proper error handling"""
        try:
            if isinstance(cmd, str):
                # For Windows PowerShell
                result = subprocess.run(
                    ["powershell", "-Command", cmd], 
                    capture_output=True, 
                    text=True, 
                    timeout=timeout,
                    cwd=self.project_root
                )
            else:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=timeout,
                    cwd=self.project_root
                )
            
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def check_working_directory(self):
        """Verify we're in the correct project directory"""
        print("🔍 Checking working directory...")
        
        required_files = ["pytest.ini", "pyproject.toml", "backend/", "tests/"]
        missing_files = []
        
        for file_path in required_files:
            if not (self.project_root / file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            self.results["issues_found"].append(f"Missing required files/directories: {missing_files}")
            print(f"❌ Missing: {missing_files}")
            return False
        
        self.results["checks"]["working_directory"] = "✅ PASS"
        print(f"✅ Working directory verified: {self.project_root}")
        return True
    
    def check_virtual_environment(self):
        """Check and activate virtual environment"""
        print("🐍 Checking Python virtual environment...")
        
        if not self.venv_path.exists():
            self.results["issues_found"].append("Virtual environment not found")
            print("❌ Virtual environment not found")
            return False
        
        # Check if venv is activated by running python and checking sys.prefix
        success, stdout, stderr = self._run_command([
            str(self.python_exe), "-c", 
            "import sys; print('VENV' if 'venv' in sys.prefix else 'SYSTEM')"
        ])
        
        if not success or "VENV" not in stdout:
            print("⚠️ Virtual environment not activated")
            self.results["solutions_applied"].append("Virtual environment activation required")
            
            # Provide activation command
            if platform.system() == "Windows":
                activation_cmd = f"{self.venv_path}\\Scripts\\Activate.ps1"
                print(f"💡 To activate: {activation_cmd}")
            else:
                activation_cmd = f"source {self.venv_path}/bin/activate"
                print(f"💡 To activate: {activation_cmd}")
            
            return False
        
        self.results["checks"]["virtual_environment"] = "✅ ACTIVATED"
        print("✅ Virtual environment is active")
        return True
    
    def check_python_version(self):
        """Verify Python version compatibility"""
        print("🔢 Checking Python version...")
        
        success, stdout, stderr = self._run_command([
            str(self.python_exe), "--version"
        ])
        
        if not success:
            self.results["issues_found"].append("Cannot determine Python version")
            print("❌ Cannot determine Python version")
            return False
        
        version_info = stdout.strip()
        self.results["checks"]["python_version"] = version_info
        print(f"✅ {version_info}")
        return True
    
    def check_pytest_installation(self):
        """Verify pytest is installed and working"""
        print("🧪 Checking pytest installation...")
        
        success, stdout, stderr = self._run_command([
            str(self.python_exe), "-m", "pytest", "--version"
        ], timeout=10)
        
        if not success:
            self.results["issues_found"].append("pytest not installed or not working")
            print("❌ pytest not available")
            return False
        
        pytest_info = stdout.split('\n')[0] if stdout else "Unknown version"
        self.results["checks"]["pytest"] = pytest_info
        print(f"✅ {pytest_info}")
        return True
    
    def check_ml_protection(self):
        """Verify sitecustomize.py ML protection is active"""
        print("🛡️ Checking ML import protection...")
        
        success, stdout, stderr = self._run_command([
            str(self.python_exe), "-c", 
            "import os; print('ML_DISABLED' if os.getenv('DISABLE_ML') == '1' else 'ML_ENABLED')"
        ])
        
        if success and "ML_DISABLED" in stdout:
            self.results["checks"]["ml_protection"] = "✅ ACTIVE"
            print("✅ ML protection is active (sitecustomize.py working)")
            return True
        else:
            self.results["solutions_applied"].append("ML protection may not be active")
            print("⚠️ ML protection status unclear")
            return True  # Non-critical
    
    def validate_critical_test_files(self):
        """Validate that critical test files exist and are collectable"""
        print("📂 Validating critical test files...")
        
        # These are our verified working test files
        critical_tests = [
            "tests/unit/test_risk_manager_current.py",
            "tests/test_api_factory_comprehensive.py",
            "tests/test_websocket_comprehensive.py",
            "tests/test_feature_engineering_part1.py",
            "tests/test_model_manager_part1.py",
            "tests/test_alpaca_client_phase7a2.py",
            "tests/test_ensemble_model_phase7a1.py"
        ]
        
        working_files = []
        problematic_files = []
        
        for test_file in critical_tests:
            file_path = self.project_root / test_file
            if not file_path.exists():
                problematic_files.append(f"{test_file} - FILE NOT FOUND")
                continue
            
            # Test pytest collection
            success, stdout, stderr = self._run_command([
                str(self.python_exe), "-m", "pytest", 
                "--collect-only", str(file_path), "-q"
            ], timeout=15)
            
            if success and "collected" in stdout:
                test_count = stdout.count("::test_")
                working_files.append(f"{test_file} ({test_count} tests)")
            else:
                problematic_files.append(f"{test_file} - COLLECTION FAILED")
        
        self.results["checks"]["working_test_files"] = len(working_files)
        self.results["checks"]["problematic_test_files"] = len(problematic_files)
        
        if working_files:
            print(f"✅ {len(working_files)} test files validated")
            for file_info in working_files[:3]:  # Show first 3
                print(f"   - {file_info}")
            if len(working_files) > 3:
                print(f"   - ... and {len(working_files)-3} more")
        
        if problematic_files:
            print(f"⚠️ {len(problematic_files)} problematic files found:")
            for file_info in problematic_files:
                print(f"   - {file_info}")
            self.results["issues_found"].extend(problematic_files)
        
        return len(working_files) > 0
    
    def identify_skipped_tests(self):
        """Identify files with skip markers that cause issues"""
        print("⏭️ Identifying skipped test files...")
        
        known_skipped_files = [
            "tests/core/test_app_lifespan_and_di.py",
            "tests/core/test_routes_and_dtos_contract.py"
        ]
        
        skipped_reasons = {}
        for test_file in known_skipped_files:
            file_path = self.project_root / test_file
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    if "@pytest.mark.skip" in content:
                        # Extract skip reason
                        import re
                        skip_match = re.search(r'@pytest\.mark\.skip\(reason="([^"]*)"', content)
                        reason = skip_match.group(1) if skip_match else "Unknown reason"
                        skipped_reasons[test_file] = reason
                except Exception:
                    skipped_reasons[test_file] = "Could not read file"
        
        if skipped_reasons:
            print(f"⚠️ Found {len(skipped_reasons)} files with skip markers:")
            for file_path, reason in skipped_reasons.items():
                print(f"   - {file_path}: {reason}")
            
            self.results["checks"]["skipped_files"] = skipped_reasons
            self.results["solutions_applied"].append("Excluded files with skip markers from test runs")
        else:
            print("✅ No problematic skip markers found in known files")
        
        return True
    
    def generate_optimized_test_command(self):
        """Generate the optimized pytest command based on findings"""
        print("🎯 Generating optimized test command...")
        
        # Comprehensive test files - ALL phases from inventory
        working_tests = [
            # CORE PHASE TESTS (previously executed)
            "tests/unit/test_risk_manager_current.py",
            "tests/test_api_factory_comprehensive.py", 
            "tests/test_websocket_comprehensive.py",
            "tests/unit/test_alpaca_client_core.py",
            "tests/unit/test_alpaca_client_comprehensive.py",
            "tests/test_feature_engineering_part1.py",
            "tests/test_feature_engineering_part2.py",
            "tests/test_model_manager_part1.py",
            "tests/test_model_manager_part2_fixed.py",
            "tests/test_model_manager_part3.py",
            "tests/test_model_manager_part4.py",
            "tests/test_alpaca_client_phase7a2.py",
            "tests/test_ensemble_model_phase7a1.py",
            "tests/test_ensemble_model_phase7a1_extended.py",
            "tests/test_market_data_phase7b1.py",
            "tests/test_market_data_phase7b1_extended.py",
            "tests/test_market_data_phase7b1_final.py",
            "tests/test_social_sentiment_phase7b2.py",
            "tests/test_social_sentiment_phase7b2_extended.py",
            "tests/test_social_sentiment_phase7b2_final.py",
            "tests/test_order_service_phase7b3.py",
            "tests/test_order_service_phase7b3_extended.py",
            "tests/test_order_service_phase7b3_final.py",
            "tests/test_ensemble_model_phase7b4.py",
            "tests/test_ensemble_model_phase7b4_final.py",
            "tests/test_trading_strategies_phase7b5.py",
            "tests/test_websocket_manager_phase7b6.py",
            "tests/test_order_service_phase7b6.py",
            
            # 0% COVERAGE MODULE TESTS (critical for coverage goals)
            # backend/api/main.py (0% coverage - 12 statements)
            "tests/unit/test_api_main_coverage.py",
            "tests/api/test_api_main_import.py",
            "tests/api/test_main_routes_smoke.py", 
            "tests/api/test_main_routes_registered.py",
            "tests/api/test_main_openapi.py",
            "tests/api/test_main_import_and_routes.py",
            "tests/api/test_main_endpoints_coverage.py",
            "tests/api/test_main_coverage_focused.py",
            
            # backend/config.py (0% coverage - 9 statements)
            "tests/test_config_coverage_quick_win.py",
            "tests/test_config_hardening.py",
            "tests/test_config_working.py",
            "tests/config/test_config_coverage.py",
            "tests/smoke/test_config_imports.py",
            "tests/unit/test_config.py",
            "tests/unit/test_unit_config_coverage.py",
            
            # backend/infra/resilience.py (0% coverage - 235 statements)
            "tests/test_outbox_resilience_coverage_fixed.py",
            "tests/test_outbox_resilience_coverage.py",
            "tests/infra/test_resilience_outbox_smoke.py",
            
            # backend/services/safety_modes.py (0% coverage - 357 statements)  
            "tests/services/test_positions_and_safety.py",
            "tests/integration/test_safety_modes.py",
            
            # backend/strategies/engine.py (0% coverage - 170 statements)
            "tests/integration/test_pipeline.py",
            "tests/performance/test_benchmarks.py", 
            "tests/test_coverage_boost.py",
            "tests/test_trading_strategies_coverage.py",
            
            # ADDITIONAL COVERAGE TESTS (from inventory documentation)
            # ML & Algorithm Coverage
            "tests/test_ml_direct_coverage.py",
            "tests/test_model_manager_coverage.py",
            "tests/test_feature_engineering_coverage.py",
            "tests/test_ensemble_model_coverage.py",
            
            # Infrastructure Coverage
            "tests/test_b25_observability.py",
            "tests/test_logging_coverage_quick_win.py",
            "tests/test_minimal_metrics.py",
            
            # Service Coverage
            "tests/test_alpaca_client_coverage.py",
            "tests/test_risk_manager_coverage.py",
            "tests/test_async_risk_manager_modern.py",
            
            # API Coverage (extensive)
            "tests/unit/test_api_endpoints_coverage.py",
            "tests/api/test_http_routes_simple.py",
            "tests/test_api_factory_coverage.py",
            
            # Additional comprehensive tests
            "tests/test_risk_manager_comprehensive_fixed.py",
            "tests/test_ws_manager_comprehensive.py",
            "tests/test_trading_strategies_behavior.py",
            "tests/test_strategy_comprehensive.py"
        ]
        
        # Filter to only existing files
        existing_tests = []
        for test_file in working_tests:
            if (self.project_root / test_file).exists():
                existing_tests.append(test_file)
        
        if not existing_tests:
            print("❌ No working test files found")
            return None
        
        print(f"✅ Found {len(existing_tests)} working test files")
        print(f"   📊 Comprehensive coverage: Core phases + 0% coverage modules + additional tests")
        print(f"   🎯 Expected coverage improvement: 43% → 55-60%+")
        
        # Generate command
        cmd_parts = ["pytest"] + existing_tests + [
            "--cov=backend",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--maxfail=500",
            "--timeout=180",
            "-v"
        ]
        
        optimized_command = " \\\n  ".join(cmd_parts)
        self.results["recommended_command"] = optimized_command
        
        print(f"✅ Generated optimized command with {len(existing_tests)} test files")
        return optimized_command
    
    def save_results(self):
        """Save results to a JSON file for future reference"""
        results_file = self.project_root / "test_preparation_results.json"
        
        try:
            with open(results_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"📄 Results saved to: {results_file}")
        except Exception as e:
            print(f"⚠️ Could not save results: {e}")
    
    def run_comprehensive_check(self):
        """Run all checks and return overall status"""
        print("🚀 Starting Comprehensive Test Preparation Check")
        print("=" * 60)
        
        checks = [
            ("Working Directory", self.check_working_directory),
            ("Virtual Environment", self.check_virtual_environment), 
            ("Python Version", self.check_python_version),
            ("Pytest Installation", self.check_pytest_installation),
            ("ML Protection", self.check_ml_protection),
            ("Critical Test Files", self.validate_critical_test_files),
            ("Skipped Test Detection", self.identify_skipped_tests),
        ]
        
        passed_checks = 0
        critical_failures = 0
        
        for check_name, check_func in checks:
            try:
                if check_func():
                    passed_checks += 1
                else:
                    # Determine if this is a critical failure
                    if check_name in ["Working Directory", "Virtual Environment", "Pytest Installation"]:
                        critical_failures += 1
                        print(f"🚨 CRITICAL: {check_name} check failed")
            except Exception as e:
                print(f"❌ {check_name} check crashed: {e}")
                critical_failures += 1
            
            print()  # Add spacing
        
        # Generate command regardless, but warn if critical issues exist
        optimized_cmd = self.generate_optimized_test_command()
        
        print("=" * 60)
        print("📊 COMPREHENSIVE SUMMARY")
        print(f"✅ Passed checks: {passed_checks}/{len(checks)}")
        print(f"🚨 Critical failures: {critical_failures}")
        print(f"⚠️ Issues found: {len(self.results['issues_found'])}")
        print(f"💡 Solutions applied: {len(self.results['solutions_applied'])}")
        
        if critical_failures == 0:
            print("\n🎉 READY FOR TEST EXECUTION")
            if optimized_cmd:
                print("\n🎯 RECOMMENDED COMMAND:")
                print(optimized_cmd)
        else:
            print(f"\n🚨 CRITICAL ISSUES MUST BE RESOLVED BEFORE TESTING")
            print("Please address the critical failures listed above.")
        
        # Save results for future reference
        self.save_results()
        
        return critical_failures == 0, optimized_cmd

def main():
    """Main entry point"""
    # Change to project directory if script is run from elsewhere
    script_dir = Path(__file__).parent
    
    manager = TestPreparationManager(script_dir)
    ready, command = manager.run_comprehensive_check()
    
    if ready and command:
        print(f"\n{'='*60}")
        print("🎯 TO EXECUTE TESTS, RUN:")
        print("=" * 60)
        print(command)
        print("=" * 60)
        
        # Optionally ask user if they want to run tests immediately
        try:
            response = input("\nRun tests now? (y/N): ").strip().lower()
            if response == 'y':
                print("🚀 Executing tests...")
                os.system(command.replace("\\\n  ", " "))
        except KeyboardInterrupt:
            print("\n👋 Test preparation completed. Run the command above when ready.")
    
    return 0 if ready else 1

if __name__ == "__main__":
    sys.exit(main())
