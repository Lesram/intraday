"""
Enhanced Terminal Output Module for Test Suites
Windows-compatible visual enhancements without problematic Unicode characters
"""
import sys
import time
from typing import Optional
from datetime import datetime


class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright foreground colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'


class TestOutput:
    """Enhanced test output with visual progress tracking"""
    
    @staticmethod
    def header(title: str, width: int = 80):
        """Print a fancy header"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * width}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{title.center(width)}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{'=' * width}{Colors.RESET}\n")
    
    @staticmethod
    def subheader(title: str, width: int = 80):
        """Print a subheader"""
        print(f"\n{Colors.BLUE}{'-' * width}{Colors.RESET}")
        print(f"{Colors.BLUE}{Colors.BOLD} {title}{Colors.RESET}")
        print(f"{Colors.BLUE}{'-' * width}{Colors.RESET}")
    
    @staticmethod
    def phase(number: int, name: str, description: str):
        """Print a phase header"""
        print(f"\n{Colors.MAGENTA}{Colors.BOLD}[PHASE {number}] {name}{Colors.RESET}")
        print(f"{Colors.BRIGHT_BLACK}>> {description}{Colors.RESET}")
        print(f"{Colors.MAGENTA}{'~' * 70}{Colors.RESET}")
    
    @staticmethod
    def test_start(name: str):
        """Print test start message"""
        print(f"\n{Colors.CYAN}[TEST]{Colors.RESET} {name}...", end='', flush=True)
    
    @staticmethod
    def test_pass(name: str, duration_ms: float, details: str = ""):
        """Print test pass message"""
        duration_str = f"{duration_ms:.0f}ms" if duration_ms < 1000 else f"{duration_ms/1000:.1f}s"
        print(f"\r{Colors.GREEN}[ OK ]{Colors.RESET} {name} {Colors.BRIGHT_BLACK}({duration_str}){Colors.RESET}")
        if details:
            print(f"      {Colors.BRIGHT_BLACK}+--> {details}{Colors.RESET}")
    
    @staticmethod
    def test_fail(name: str, error: str):
        """Print test fail message"""
        print(f"\r{Colors.RED}[FAIL]{Colors.RESET} {name}")
        print(f"      {Colors.RED}+--> Error: {error}{Colors.RESET}")
    
    @staticmethod
    def test_skip(name: str, reason: str = ""):
        """Print test skip message"""
        print(f"\r{Colors.YELLOW}[SKIP]{Colors.RESET} {name}")
        if reason:
            print(f"      {Colors.BRIGHT_BLACK}+--> {reason}{Colors.RESET}")
    
    @staticmethod
    def progress(current: int, total: int, label: str = "Progress"):
        """Print a progress bar"""
        percentage = (current / total) * 100 if total > 0 else 0
        filled = int(percentage / 2)  # 50 chars wide
        bar = '#' * filled + '-' * (50 - filled)
        
        print(f"\r{Colors.CYAN}{label}:{Colors.RESET} [{bar}] {percentage:.1f}% ({current}/{total})", 
              end='', flush=True)
        
        if current == total:
            print()  # New line when complete
    
    @staticmethod
    def spinner(message: str, step: int):
        """Print a spinner animation"""
        simple_spinners = ['|', '/', '-', '\\']
        char = simple_spinners[step % len(simple_spinners)]
        print(f"\r{Colors.CYAN}{char}{Colors.RESET} {message}...", end='', flush=True)
    
    @staticmethod
    def summary_box(title: str, items: list, width: int = 70):
        """Print a summary box"""
        print(f"\n{Colors.BOLD}{Colors.WHITE}+{'-' * (width - 2)}+{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.WHITE}| {title.center(width - 4)} |{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.WHITE}+{'=' * (width - 2)}+{Colors.RESET}")
        
        for item in items:
            if isinstance(item, str):
                print(f"{Colors.WHITE}|{Colors.RESET} {item.ljust(width - 4)} {Colors.WHITE}|{Colors.RESET}")
            elif isinstance(item, dict):
                label = item.get('label', '')
                value = item.get('value', '')
                color = item.get('color', Colors.WHITE)
                print(f"{Colors.WHITE}|{Colors.RESET} {label.ljust(40)} {color}{str(value).rjust(width - 47)}{Colors.RESET} {Colors.WHITE}|{Colors.RESET}")
        
        print(f"{Colors.BOLD}{Colors.WHITE}+{'-' * (width - 2)}+{Colors.RESET}\n")
    
    @staticmethod
    def metric(label: str, value: str, color=Colors.WHITE, unit: str = ""):
        """Print a metric line"""
        full_value = f"{value} {unit}".strip()
        print(f"  {Colors.BRIGHT_BLACK}*{Colors.RESET} {label.ljust(35)} {color}{full_value}{Colors.RESET}")
    
    @staticmethod
    def success(message: str):
        """Print success message"""
        print(f"\n{Colors.GREEN}{Colors.BOLD}[SUCCESS]{Colors.RESET} {message}")
    
    @staticmethod
    def error(message: str):
        """Print error message"""
        print(f"\n{Colors.RED}{Colors.BOLD}[ERROR]{Colors.RESET} {message}")
    
    @staticmethod
    def warning(message: str):
        """Print warning message"""
        print(f"\n{Colors.YELLOW}{Colors.BOLD}[WARNING]{Colors.RESET} {message}")
    
    @staticmethod
    def info(message: str):
        """Print info message"""
        print(f"{Colors.CYAN}[INFO]{Colors.RESET} {message}")
    
    @staticmethod
    def section_divider(char: str = '-', width: int = 80):
        """Print a section divider"""
        print(f"{Colors.BRIGHT_BLACK}{char * width}{Colors.RESET}")
    
    @staticmethod
    def timestamp():
        """Return formatted timestamp"""
        return datetime.now().strftime("%H:%M:%S")
    
    @staticmethod
    def test_summary(passed: int, failed: int, skipped: int = 0, duration_sec: float = 0):
        """Print test execution summary"""
        total = passed + failed + skipped
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        # Determine overall status color
        if failed == 0 and skipped == 0:
            status_color = Colors.GREEN
            status_text = "ALL TESTS PASSED"
        elif failed == 0:
            status_color = Colors.YELLOW
            status_text = "TESTS PASSED (WITH SKIPS)"
        else:
            status_color = Colors.RED
            status_text = "SOME TESTS FAILED"
        
        items = [
            {'label': 'Total Tests', 'value': total, 'color': Colors.CYAN},
            {'label': 'Passed', 'value': f'{passed} ({pass_rate:.1f}%)', 'color': Colors.GREEN},
            {'label': 'Failed', 'value': failed, 'color': Colors.RED if failed > 0 else Colors.GREEN},
        ]
        
        if skipped > 0:
            items.append({'label': 'Skipped', 'value': skipped, 'color': Colors.YELLOW})
        
        if duration_sec > 0:
            duration_str = f"{duration_sec:.1f}s" if duration_sec < 60 else f"{duration_sec/60:.1f}min"
            items.append({'label': 'Duration', 'value': duration_str, 'color': Colors.CYAN})
        
        TestOutput.summary_box(f"{status_color}{status_text}{Colors.RESET}", items, width=70)
    
    @staticmethod
    def layer_header(layer_num: int, layer_name: str, layer_icon: str = ">"):
        """Print layer header"""
        print(f"\n{Colors.MAGENTA}{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.MAGENTA}{Colors.BOLD}{layer_icon} LAYER {layer_num}: {layer_name}{Colors.RESET}")
        print(f"{Colors.MAGENTA}{Colors.BOLD}{'=' * 80}{Colors.RESET}")
    
    @staticmethod
    def workflow_start(workflow_name: str, step: int, total: int):
        """Print workflow start"""
        print(f"\n{Colors.CYAN}[{step}/{total}]{Colors.RESET} {Colors.BOLD}{workflow_name}{Colors.RESET}")
        print(f"{Colors.BRIGHT_BLACK}{'-' * 60}{Colors.RESET}")
    
    @staticmethod
    def ascii_art_success():
        """Print ASCII art for success"""
        art = f"""
{Colors.GREEN}{Colors.BOLD}
    +=======================================+
    |                                       |
    |       [  S U C C E S S  ]             |
    |                                       |
    |     All tests passed successfully!    |
    |                                       |
    +=======================================+
{Colors.RESET}
        """
        print(art)
    
    @staticmethod
    def ascii_art_partial():
        """Print ASCII art for partial success"""
        art = f"""
{Colors.YELLOW}{Colors.BOLD}
    +=======================================+
    |                                       |
    |      [  P A R T I A L   P A S S  ]    |
    |                                       |
    |    Some tests need attention          |
    |                                       |
    +=======================================+
{Colors.RESET}
        """
        print(art)
    
    @staticmethod
    def ascii_art_fail():
        """Print ASCII art for failure"""
        art = f"""
{Colors.RED}{Colors.BOLD}
    +=======================================+
    |                                       |
    |          [  F A I L E D  ]            |
    |                                       |
    |      Tests require fixes              |
    |                                       |
    +=======================================+
{Colors.RESET}
        """
        print(art)


# Convenience functions for quick access
def print_test_start(name: str):
    TestOutput.test_start(name)

def print_test_pass(name: str, duration_ms: float, details: str = ""):
    TestOutput.test_pass(name, duration_ms, details)

def print_test_fail(name: str, error: str):
    TestOutput.test_fail(name, error)

def print_progress(current: int, total: int, label: str = "Progress"):
    TestOutput.progress(current, total, label)
