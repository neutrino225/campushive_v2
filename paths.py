from pathlib import Path

# Resolve repository root based on this file's location
REPO_ROOT = Path(__file__).resolve().parent


def repo_root() -> Path:
    return REPO_ROOT


def data_dir() -> Path:
    """Absolute path to the top-level data directory."""
    return REPO_ROOT / "data"


def data_subdir(name: str) -> Path:
    """Return an absolute path to a named subdirectory under data/, creating it if needed."""
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


__all__ = ["repo_root", "data_dir", "data_subdir", "ensure_dir"]
