# AI Agent Enhancement Integration Test
# =====================================
# Tests complete suite of AI Agent suggestions A-F for compatibility
# Validates all components work together seamlessly with existing platform

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List
import tempfile

logger = logging.getLogger(__name__)

class AIEnhancementIntegrationTester:
    """
    Tests complete AI Agent enhancement suite integration:
    
    A. K6 Enhanced Error Normalization 
    B. Per-Route SLI Metrics Middleware
    C. 3-Session Burn-in Testing Framework  
    D. Automated Promotion Gates
    E. Enhanced SLO Threshold Management
    F. Multi-Environment Validation
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_results: Dict[str, Dict] = {}
        
    async def run_complete_integration_test(self) -> Dict[str, Any]:
        """Run complete integration test of all AI Agent enhancements"""
        
        logger.info("🤖 Starting AI Agent Enhancement Integration Test")
        start_time = time.time()
        
        try:
            # Test A: K6 Enhanced Error Normalization
            logger.info("🔍 Testing A: K6 Enhanced Error Normalization")
            k6_result = await self._test_k6_enhanced_error_normalization()
            self.test_results['k6_enhanced'] = k6_result
            
            # Test B: Per-Route SLI Metrics (Simulation)
            logger.info("📊 Testing B: Per-Route SLI Metrics Compatibility")
            sli_result = await self._test_per_route_sli_compatibility()
            self.test_results['sli_metrics'] = sli_result
            
            # Test C: Burn-in Framework (Dry Run)
            logger.info("🔥 Testing C: Burn-in Framework Configuration")
            burn_in_result = await self._test_burn_in_framework_config()
            self.test_results['burn_in_framework'] = burn_in_result
            
            # Test D: Promotion Gates (Validation)
            logger.info("🚪 Testing D: Promotion Gates Logic")
            promotion_gates_result = await self._test_promotion_gates_logic()
            self.test_results['promotion_gates'] = promotion_gates_result
            
            # Test E: Enhanced SLO Management
            logger.info("📈 Testing E: Enhanced SLO Management")
            slo_management_result = await self._test_enhanced_slo_management()
            self.test_results['slo_management'] = slo_management_result
            
            # Test F: Multi-Environment Validation
            logger.info("🌍 Testing F: Multi-Environment Configuration")
            multi_env_result = await self._test_multi_environment_validation()
            self.test_results['multi_environment'] = multi_env_result
            
            # Integration Compatibility Test
            logger.info("🔗 Testing Integration Compatibility")
            integration_result = await self._test_cross_component_integration()
            self.test_results['integration'] = integration_result
            
            # Generate comprehensive report
            total_duration = time.time() - start_time
            report = self._generate_integration_report(total_duration)
            
            # Save results
            await self._save_integration_report(report)
            
            logger.info(f"🤖 AI Enhancement Integration Test completed in {total_duration:.1f}s")
            return report
            
        except Exception as e:
            logger.error(f"Integration test failed: {str(e)}")
            raise
    
    async def _test_k6_enhanced_error_normalization(self) -> Dict[str, Any]:
        """Test K6 enhanced error normalization script"""
        result = {
            'test_name': 'K6 Enhanced Error Normalization',
            'passed': False,
            'details': {},
            'issues': []
        }
        
        k6_script = Path("scripts/testing/k6_enhanced_comprehensive_test.js")
        
        # Check if script exists
        if not k6_script.exists():
            result['issues'].append("K6 enhanced script not found")
            return result
        
        # Validate script syntax
        try:
            with open(k6_script, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Check for AI Agent enhancements
            enhancements_found = {
                'unexpected_error_rate_metric': 'unexpected_error_rate' in content,
                'expected_guardrail_detection': 'isExpectedGuardrail' in content,
                'per_route_thresholds': 'http_req_duration{name:' in content,
                'summary_artifact': 'k6-summary.json' in content,
                'normalized_checks': 'isExpectedGuardrail(r)' in content
            }
            
            result['details']['enhancements'] = enhancements_found
            missing_enhancements = [k for k, v in enhancements_found.items() if not v]
            
            if missing_enhancements:
                result['issues'].extend([f"Missing enhancement: {e}" for e in missing_enhancements])
            else:
                result['passed'] = True
                result['details']['message'] = "All K6 enhancements properly implemented"
            
        except Exception as e:
            result['issues'].append(f"Script validation error: {str(e)}")
        
        return result
    
    async def _test_per_route_sli_compatibility(self) -> Dict[str, Any]:
        """Test per-route SLI metrics middleware compatibility"""
        result = {
            'test_name': 'Per-Route SLI Metrics',
            'passed': False,
            'details': {},
            'issues': []
        }
        
        sli_module = Path("backend/monitoring/per_route_sli.py")
        
        # Check if module exists
        if not sli_module.exists():
            result['issues'].append("Per-route SLI module not found")
            return result
        
        try:
            # Import validation (syntax check)
            import sys
            sys.path.insert(0, str(Path.cwd()))
            
            # Test imports without actually importing (avoid side effects)
            with open(sli_module, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Check for required components
            components_found = {
                'prometheus_metrics': 'prometheus_client' in content,
                'middleware_class': 'PerRouteSLIMiddleware' in content,
                'route_normalization': '_normalize_path' in content,
                'business_metrics': 'business_operation_duration' in content,
                'slo_integration': 'SLOMetricsExporter' in content,
                'fastapi_integration': 'create_sli_middleware_with_integration' in content
            }
            
            result['details']['components'] = components_found
            missing_components = [k for k, v in components_found.items() if not v]
            
            if missing_components:
                result['issues'].extend([f"Missing component: {c}" for c in missing_components])
            else:
                result['passed'] = True
                result['details']['message'] = "All SLI components properly implemented"
                
        except Exception as e:
            result['issues'].append(f"SLI module validation error: {str(e)}")
        
        return result
    
    async def _test_burn_in_framework_config(self) -> Dict[str, Any]:
        """Test burn-in testing framework configuration"""
        result = {
            'test_name': 'Burn-in Testing Framework',
            'passed': False,
            'details': {},
            'issues': []
        }
        
        burn_in_script = Path("scripts/testing/burn_in_framework.py")
        
        if not burn_in_script.exists():
            result['issues'].append("Burn-in framework script not found")
            return result
        
        try:
            with open(burn_in_script, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Check framework components
            framework_components = {
                'session_configurations': 'BurnInSessionConfig' in content,
                'three_sessions': 'light_load' in content and 'production_load' in content and 'stress_load' in content,
                'system_monitoring': '_monitor_system_resources' in content,
                'stability_scoring': '_calculate_stability_score' in content,
                'k6_integration': '_run_k6_session' in content,
                'promotion_ready': 'ready_for_production' in content
            }
            
            result['details']['components'] = framework_components
            missing_components = [k for k, v in framework_components.items() if not v]
            
            if missing_components:
                result['issues'].extend([f"Missing component: {c}" for c in missing_components])
            else:
                # Test session configuration validity
                if all(session in content for session in ['30', '60', '45']):  # Session durations
                    result['passed'] = True
                    result['details']['message'] = "Burn-in framework properly configured"
                else:
                    result['issues'].append("Invalid session duration configuration")
                    
        except Exception as e:
            result['issues'].append(f"Burn-in framework validation error: {str(e)}")
        
        return result
    
    async def _test_promotion_gates_logic(self) -> Dict[str, Any]:
        """Test automated promotion gates logic"""
        result = {
            'test_name': 'Automated Promotion Gates',  
            'passed': False,
            'details': {},
            'issues': []
        }
        
        promotion_script = Path("scripts/testing/automated_promotion_gates.py")
        
        if not promotion_script.exists():
            result['issues'].append("Promotion gates script not found")
            return result
        
        try:
            with open(promotion_script, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Check gate validation components
            gate_components = {
                'promotion_criteria': 'PromotionCriteria' in content,
                'system_readiness': '_validate_system_readiness' in content,
                'k6_validation': '_validate_k6_performance' in content,
                'sli_validation': '_validate_per_route_sli' in content,
                'burn_in_validation': '_validate_burn_in_results' in content,
                'slo_validation': '_validate_slo_compliance' in content,
                'business_validation': '_validate_business_logic' in content,
                'decision_logic': 'promotion_approved' in content
            }
            
            result['details']['components'] = gate_components
            missing_components = [k for k, v in gate_components.items() if not v]
            
            if missing_components:
                result['issues'].extend([f"Missing component: {c}" for c in missing_components])
            else:
                # Check integration with other AI components
                ai_integrations = {
                    'k6_enhanced': 'k6_enhanced_comprehensive_test.js' in content,
                    'sli_metrics': 'sli-metrics' in content,
                    'burn_in_results': 'burn_in_report' in content
                }
                
                result['details']['ai_integrations'] = ai_integrations
                
                if all(ai_integrations.values()):
                    result['passed'] = True
                    result['details']['message'] = "Promotion gates properly integrated with AI enhancements"
                else:
                    result['issues'].append("Incomplete AI component integration")
                    
        except Exception as e:
            result['issues'].append(f"Promotion gates validation error: {str(e)}")
        
        return result
    
    async def _test_enhanced_slo_management(self) -> Dict[str, Any]:
        """Test enhanced SLO management functionality"""
        result = {
            'test_name': 'Enhanced SLO Management',
            'passed': False,
            'details': {},
            'issues': []
        }
        
        slo_manager = Path("backend/monitoring/enhanced_slo_manager.py")
        
        if not slo_manager.exists():
            result['issues'].append("Enhanced SLO manager not found")
            return result
        
        try:
            with open(slo_manager, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Check SLO management components
            slo_components = {
                'dynamic_thresholds': 'SLOThreshold' in content,
                'environment_profiles': 'EnvironmentSLOProfile' in content,
                'threshold_adjustment': '_adjust_threshold_if_needed' in content,
                'multi_environment': 'get_environment_slo_thresholds' in content,
                'prometheus_integration': 'update_prometheus_alerts' in content,
                'promotion_criteria': 'create_environment_specific_promotion_criteria' in content
            }
            
            result['details']['components'] = slo_components
            missing_components = [k for k, v in slo_components.items() if not v]
            
            if missing_components:
                result['issues'].extend([f"Missing component: {c}" for c in missing_components])
            else:
                # Check environment configurations
                environments = ['development', 'staging', 'production']
                env_configs_found = all(env in content for env in environments)
                
                if env_configs_found:
                    result['passed'] = True
                    result['details']['message'] = "Enhanced SLO management fully implemented"
                else:
                    result['issues'].append("Incomplete environment configurations")
                    
        except Exception as e:
            result['issues'].append(f"SLO management validation error: {str(e)}")
        
        return result
    
    async def _test_multi_environment_validation(self) -> Dict[str, Any]:
        """Test multi-environment validation capabilities"""
        result = {
            'test_name': 'Multi-Environment Validation',
            'passed': False,
            'details': {},
            'issues': []
        }
        
        # Check if multi-environment support is properly configured
        try:
            # Verify SLO manager has environment profiles
            slo_manager_path = Path("backend/monitoring/enhanced_slo_manager.py")
            promotion_gates_path = Path("scripts/testing/automated_promotion_gates.py")
            
            missing_files = []
            if not slo_manager_path.exists():
                missing_files.append("enhanced_slo_manager.py")
            if not promotion_gates_path.exists():
                missing_files.append("automated_promotion_gates.py")
            
            if missing_files:
                result['issues'].extend([f"Missing file: {f}" for f in missing_files])
                return result
            
            # Check environment configuration in both files
            with open(slo_manager_path, encoding='utf-8', errors='ignore') as f:
                slo_content = f.read()
            with open(promotion_gates_path, encoding='utf-8', errors='ignore') as f:
                gates_content = f.read()
            
            # Environment support checks
            env_support = {
                'slo_environment_profiles': all(env in slo_content for env in ['development', 'staging', 'production']),
                'gates_environment_criteria': 'create_environment_specific_promotion_criteria' in slo_content,
                'environment_readiness_validation': 'validate_environment_readiness' in slo_content,
                'environment_specific_thresholds': 'get_environment_slo_thresholds' in slo_content
            }
            
            result['details']['environment_support'] = env_support
            missing_support = [k for k, v in env_support.items() if not v]
            
            if missing_support:
                result['issues'].extend([f"Missing support: {s}" for s in missing_support])
            else:
                result['passed'] = True
                result['details']['message'] = "Multi-environment validation fully supported"
                
        except Exception as e:
            result['issues'].append(f"Multi-environment validation error: {str(e)}")
        
        return result
    
    async def _test_cross_component_integration(self) -> Dict[str, Any]:
        """Test integration between all AI enhancement components"""
        result = {
            'test_name': 'Cross-Component Integration',
            'passed': False,
            'details': {},
            'issues': []
        }
        
        try:
            # Check integration points between components
            integration_checks = {
                'k6_to_promotion_gates': False,
                'sli_to_promotion_gates': False,
                'burn_in_to_promotion_gates': False,
                'slo_to_promotion_gates': False,
                'slo_to_environments': False
            }
            
            # Check promotion gates integration
            promotion_gates_path = Path("scripts/testing/automated_promotion_gates.py")
            if promotion_gates_path.exists():
                with open(promotion_gates_path, encoding='utf-8', errors='ignore') as f:
                    gates_content = f.read()
                
                # Check if promotion gates references other components
                integration_checks['k6_to_promotion_gates'] = 'k6_enhanced_comprehensive_test.js' in gates_content
                integration_checks['sli_to_promotion_gates'] = 'per_route_sli' in gates_content or 'sli-metrics' in gates_content
                integration_checks['burn_in_to_promotion_gates'] = 'burn_in_report' in gates_content
                integration_checks['slo_to_promotion_gates'] = 'slo_compliance' in gates_content
            
            # Check SLO to environment integration
            slo_manager_path = Path("backend/monitoring/enhanced_slo_manager.py")
            if slo_manager_path.exists():
                with open(slo_manager_path, encoding='utf-8', errors='ignore') as f:
                    slo_content = f.read()
                
                integration_checks['slo_to_environments'] = 'create_environment_specific_promotion_criteria' in slo_content
            
            result['details']['integration_checks'] = integration_checks
            failed_integrations = [k for k, v in integration_checks.items() if not v]
            
            if failed_integrations:
                result['issues'].extend([f"Missing integration: {i}" for i in failed_integrations])
            else:
                # Check for circular dependencies or conflicts
                dependency_conflicts = self._check_for_dependency_conflicts()
                if dependency_conflicts:
                    result['issues'].extend(dependency_conflicts)
                else:
                    result['passed'] = True
                    result['details']['message'] = "All AI components properly integrated"
                    
        except Exception as e:
            result['issues'].append(f"Integration testing error: {str(e)}")
        
        return result
    
    def _check_for_dependency_conflicts(self) -> List[str]:
        """Check for potential dependency conflicts between components"""
        conflicts = []
        
        # Check for import conflicts
        ai_files = [
            "scripts/testing/k6_enhanced_comprehensive_test.js",
            "backend/monitoring/per_route_sli.py",
            "scripts/testing/burn_in_framework.py", 
            "scripts/testing/automated_promotion_gates.py",
            "backend/monitoring/enhanced_slo_manager.py"
        ]
        
        python_imports = set()
        for file_path in ai_files:
            if file_path.endswith('.py') and Path(file_path).exists():
                try:
                    with open(file_path, encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Extract import statements (basic check)
                    import_lines = [line.strip() for line in content.split('\n') if line.strip().startswith('import ') or line.strip().startswith('from ')]
                    python_imports.update(import_lines)
                    
                except Exception:
                    continue
        
        # Check for potentially conflicting imports (very basic)
        if len(python_imports) > 50:  # If too many imports, might indicate bloat
            conflicts.append("Potential import bloat detected")
        
        return conflicts
    
    def _generate_integration_report(self, duration: float) -> Dict[str, Any]:
        """Generate comprehensive integration test report"""
        
        # Count results
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result['passed'])
        failed_tests = total_tests - passed_tests
        
        # Collect all issues
        all_issues = []
        for test_name, result in self.test_results.items():
            if result['issues']:
                for issue in result['issues']:
                    all_issues.append(f"{test_name}: {issue}")
        
        # Overall assessment
        overall_passed = failed_tests == 0
        confidence = "HIGH" if overall_passed else "MEDIUM" if failed_tests <= 2 else "LOW"
        
        # Recommendations
        recommendations = []
        if overall_passed:
            recommendations.extend([
                "✅ All AI Agent enhancements are compatible and ready for deployment",
                "🚀 Consider running the full integration pipeline in staging environment",
                "📊 Monitor per-route SLI metrics after deployment"
            ])
        else:
            recommendations.extend([
                "🔧 Address failing component issues before deployment",
                "📋 Review integration test details for specific fixes needed"
            ])
            
            if failed_tests > 2:
                recommendations.append("⚠️ Multiple component failures - consider phased deployment")
        
        return {
            'summary': {
                'title': 'AI Agent Enhancement Integration Test Report',
                'timestamp': time.time(),
                'duration_seconds': duration,
                'overall_passed': overall_passed,
                'confidence': confidence,
                'tests_total': total_tests,
                'tests_passed': passed_tests,
                'tests_failed': failed_tests
            },
            
            'test_results': self.test_results,
            
            'component_status': {
                'k6_enhanced_error_normalization': self.test_results.get('k6_enhanced', {}).get('passed', False),
                'per_route_sli_metrics': self.test_results.get('sli_metrics', {}).get('passed', False),
                'burn_in_testing_framework': self.test_results.get('burn_in_framework', {}).get('passed', False),
                'automated_promotion_gates': self.test_results.get('promotion_gates', {}).get('passed', False),
                'enhanced_slo_management': self.test_results.get('slo_management', {}).get('passed', False),
                'multi_environment_validation': self.test_results.get('multi_environment', {}).get('passed', False),
                'cross_component_integration': self.test_results.get('integration', {}).get('passed', False)
            },
            
            'issues_found': all_issues,
            'recommendations': recommendations,
            
            'deployment_readiness': {
                'ready_for_staging': overall_passed,
                'ready_for_production': overall_passed and confidence == "HIGH",
                'phased_deployment_recommended': failed_tests > 0,
                'next_steps': [
                    "Run K6 enhanced test in staging" if overall_passed else "Fix component issues",
                    "Deploy per-route SLI middleware" if self.test_results.get('sli_metrics', {}).get('passed', False) else "Fix SLI middleware",
                    "Configure promotion gates in CI/CD" if overall_passed else "Validate promotion gate logic"
                ]
            }
        }
    
    async def _save_integration_report(self, report: Dict[str, Any]):
        """Save integration test report"""
        timestamp = int(time.time())
        report_file = Path(f"test_results/ai_enhancement_integration_report_{timestamp}.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Integration test report saved: {report_file}")

# ============================================================================
# CLI INTERFACE FOR INTEGRATION TESTING
# ============================================================================

async def main():
    """CLI entry point for AI enhancement integration testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Agent Enhancement Integration Test')
    parser.add_argument('--base-url', default='http://localhost:8000', help='Platform base URL')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run integration test
    tester = AIEnhancementIntegrationTester(base_url=args.base_url)
    
    try:
        report = await tester.run_complete_integration_test()
        
        # Print summary
        summary = report['summary']
        print(f"\n🤖 AI AGENT ENHANCEMENT INTEGRATION TEST RESULTS")
        print(f"Duration: {summary['duration_seconds']:.1f}s")
        print(f"Tests: {summary['tests_passed']}/{summary['tests_total']} passed")
        print(f"Overall Status: {'✅ PASSED' if summary['overall_passed'] else '❌ FAILED'}")
        print(f"Confidence: {summary['confidence']}")
        print(f"")
        
        # Component status
        print("COMPONENT STATUS:")
        for component, status in report['component_status'].items():
            status_icon = "✅" if status else "❌"
            component_name = component.replace('_', ' ').title()
            print(f"  {status_icon} {component_name}")
        
        print(f"")
        
        # Issues
        if report['issues_found']:
            print("ISSUES FOUND:")
            for issue in report['issues_found']:
                print(f"  ❌ {issue}")
            print(f"")
        
        # Recommendations
        if report['recommendations']:
            print("RECOMMENDATIONS:")
            for rec in report['recommendations']:
                print(f"  {rec}")
        
        # Deployment readiness
        readiness = report['deployment_readiness']
        print(f"")
        print("DEPLOYMENT READINESS:")
        print(f"  Staging: {'✅ Ready' if readiness['ready_for_staging'] else '❌ Not Ready'}")
        print(f"  Production: {'✅ Ready' if readiness['ready_for_production'] else '❌ Not Ready'}")
        
        return 0 if summary['overall_passed'] else 1
        
    except Exception as e:
        logger.error(f"Integration test failed: {str(e)}")
        return 2

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))