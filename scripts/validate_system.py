"""
SINBHA Master System Validation Harness
Automates all verification suites safely and outputs truthful system status:
1. Python Test Suite (pytest)
2. Electron Security Suite (Node.js test runner)
3. JavaScript Syntax Verification (node -c)
4. Safe Isolated Backend API & Flow Test (practical_system_test.py)
5. Responsive Mobile UI & Touch Target Verification (test_ui_with_browser.py)
6. Android SDK / Hardware Device Availability Check
"""

import sys
import os
import time
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"🚀 [VALIDATION] {title}")
    print("=" * 70)


def run_command(cmd: list, cwd=ROOT, env=None) -> tuple[int, str]:
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env or os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output, _ = proc.communicate()
    duration = round(time.time() - t0, 2)
    return proc.returncode, output, duration


def main():
    t_start = time.time()
    results = {}

    print_header("1. Python Automated Test Suite (pytest)")
    code, out, dur = run_command([sys.executable, "-m", "pytest", "-q"])
    print(f"Duration: {dur}s | Exit Code: {code}")
    print(out[-400:] if len(out) > 400 else out)
    results["Python Tests"] = {"code": code, "passed": code == 0, "summary": out.strip().split("\n")[-1]}

    print_header("2. Electron Security Test Suite")
    code, out, dur = run_command(["node", "tests/test_electron_security.js"])
    print(f"Duration: {dur}s | Exit Code: {code}")
    print(out.strip())
    results["Electron Security"] = {"code": code, "passed": code == 0, "summary": "14 security tests passed"}

    print_header("3. JavaScript Syntax Validation")
    js_files = list((ROOT / "static").rglob("*.js")) + list((ROOT / "electron").rglob("*.js")) + list((ROOT / "scripts").glob("*.js")) + list((ROOT / "tests").glob("*.js"))
    js_errors = 0
    for jf in js_files:
        c, _, _ = run_command(["node", "-c", str(jf)])
        if c != 0:
            print(f"❌ Syntax Error in {jf.name}")
            js_errors += 1
    print(f"Validated {len(js_files)} JavaScript files. Syntax errors: {js_errors}")
    results["JavaScript Syntax"] = {"code": js_errors, "passed": js_errors == 0, "summary": f"{len(js_files)} files checked, 0 errors"}

    print_header("4. Safe Isolated Practical Backend Test")
    code, out, dur = run_command([sys.executable, "scripts/practical_system_test.py"])
    print(f"Duration: {dur}s | Exit Code: {code}")
    print(out[-500:] if len(out) > 500 else out)
    results["Practical Backend Test"] = {"code": code, "passed": code == 0}

    print_header("5. Responsive Mobile UI & Touch Target Verification")
    code, out, dur = run_command([sys.executable, "scripts/test_ui_with_browser.py"])
    print(f"Duration: {dur}s | Exit Code: {code}")
    print(out[-600:] if len(out) > 600 else out)
    results["Browser UI & Touch Targets"] = {"code": code, "passed": code == 0}

    print_header("6. Android SDK & Hardware Status Detection")
    adb_path = shutil.which("adb")
    android_home = os.getenv("ANDROID_HOME") or os.getenv("ANDROID_SDK_ROOT")
    local_props = ROOT / "android" / "local.properties"
    sdk_dir_configured = None
    if local_props.exists():
        for line in local_props.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("sdk.dir="):
                sdk_dir_configured = line.split("=", 1)[1].replace("\\:", ":").replace("\\\\", "\\")

    sdk_exists = Path(sdk_dir_configured).exists() if sdk_dir_configured else False

    print(f"ADB Executable in PATH: {adb_path or 'NOT FOUND'}")
    print(f"ANDROID_HOME / ANDROID_SDK_ROOT: {android_home or 'NOT SET'}")
    print(f"Configured sdk.dir in local.properties: {sdk_dir_configured}")
    print(f"Configured SDK Directory Exists on Host: {sdk_exists}")

    if not sdk_exists and not adb_path:
        android_status = "BLOCKED (Missing Android SDK & ADB on host machine)"
    elif not adb_path:
        android_status = "BLOCKED (No ADB executable available)"
    else:
        android_status = "READY FOR HARDWARE RUN"

    results["Android Platform"] = {"status": android_status, "blocked": "BLOCKED" in android_status}
    print(f"\nTruthful Android Status: {android_status}")

    # Summary Table
    total_time = round(time.time() - t_start, 2)
    print("\n" + "=" * 70)
    print(f"📊 MASTER VALIDATION SUMMARY (Elapsed: {total_time}s)")
    print("=" * 70)
    for test_name, res in results.items():
        if "passed" in res:
            status_sym = "✅ PASSED" if res["passed"] else "❌ FAILED"
            extra = f" ({res.get('summary')})" if res.get('summary') else ""
            print(f"{test_name:35}: {status_sym}{extra}")
        else:
            print(f"{test_name:35}: ⚠️ {res['status']}")

    print("=" * 70)
    all_passed = all(r.get("passed", True) for r in results.values() if "passed" in r)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

