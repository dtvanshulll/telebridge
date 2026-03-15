"""Release readiness checks for telebridge."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.1.0"
EXPECTED_DESCRIPTION = "Unified Telegram Bot and Userbot automation framework"
EXPECTED_DEPENDENCIES = {"telethon>=1.30", "aiogram>=3.0", "python-dotenv"}
REQUIRED_CLASSIFIERS = {
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
}
REQUIRED_EXAMPLES = {
    "basic_bot.py",
    "channel_automation.py",
    "userbot_login.py",
}


def load_pyproject() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def check_project_import(errors: list[str]) -> None:
    sys.path.insert(0, str(ROOT))
    try:
        package = importlib.import_module("telebridge")
    except Exception as exc:
        errors.append(f"Project import failed: {exc}")
        return

    version = getattr(package, "version", None)
    app = getattr(package, "app", None)
    if version != EXPECTED_VERSION:
        errors.append(f"Expected telebridge.version to be {EXPECTED_VERSION!r}, got {version!r}.")
    if app is None:
        errors.append("telebridge.app is not exposed from the package root.")


def check_project_files(errors: list[str]) -> None:
    for name in ("README.md", "LICENSE", "CHANGELOG.md"):
        if not (ROOT / name).exists():
            errors.append(f"Missing required project file: {name}")


def check_examples(errors: list[str]) -> None:
    examples_dir = ROOT / "examples"
    example_names = {path.name for path in examples_dir.glob("*.py")}
    missing = REQUIRED_EXAMPLES - example_names
    if missing:
        errors.append("Missing required example files: " + ", ".join(sorted(missing)))

    for example in sorted(examples_dir.glob("*.py")):
        result = subprocess.run(
            [sys.executable, "-c", f"import runpy; runpy.run_path(r'{example}', run_name='telebridge_release_check')"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown error"
            errors.append(f"Example import failed for {example.name}: {details}")


def check_pyproject_metadata(errors: list[str]) -> None:
    data = load_pyproject()
    project = data.get("project", {})

    expected_fields = {
        "name": "telebridge",
        "version": EXPECTED_VERSION,
        "description": EXPECTED_DESCRIPTION,
        "readme": "README.md",
        "requires-python": ">=3.10",
    }
    for key, expected in expected_fields.items():
        if project.get(key) != expected:
            errors.append(f"pyproject.toml field {key!r} must be {expected!r}.")

    if project.get("license") != {"text": "MIT"}:
        errors.append("pyproject.toml must declare license = { text = 'MIT' }.")

    dependencies = set(project.get("dependencies", []))
    missing_dependencies = EXPECTED_DEPENDENCIES - dependencies
    if missing_dependencies:
        errors.append(
            "pyproject.toml is missing required dependencies: "
            + ", ".join(sorted(missing_dependencies))
        )

    classifiers = set(project.get("classifiers", []))
    missing_classifiers = REQUIRED_CLASSIFIERS - classifiers
    if missing_classifiers:
        errors.append(
            "pyproject.toml is missing required classifiers: "
            + ", ".join(sorted(missing_classifiers))
        )


def main() -> int:
    errors: list[str] = []
    check_project_import(errors)
    check_project_files(errors)
    check_examples(errors)
    check_pyproject_metadata(errors)

    if errors:
        print("Release check failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Release check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
