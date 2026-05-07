from pathlib import Path


def test_project_scaffold_files_exist():
    expected = [
        Path("requirements.txt"),
        Path(".env.example"),
        Path("README.md"),
        Path("bot/__init__.py"),
        Path("tests/__init__.py"),
    ]
    missing = [str(path) for path in expected if not path.exists()]
    assert missing == []
