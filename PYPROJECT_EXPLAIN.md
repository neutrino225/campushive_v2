What is `pyproject.toml`?

`pyproject.toml` is a standardized configuration file for Python projects (PEP 518, PEP 517 and related PEPs). It provides a single place to declare the project's build system requirements and tool configuration. It is increasingly the recommended way to manage Python project metadata and tooling config.

Key uses:

- build-system: declare the backend used to build the package (e.g., `setuptools`, `poetry`, `flit`, `hatch`). Example:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
```

- packaging metadata: projects using modern build backends can put package metadata here (name, version, authors) instead of `setup.py` or `setup.cfg`.

- tool configuration: many tools read `pyproject.toml` for configuration, replacing `.flake8`, `setup.cfg`, or tool-specific config files. Examples:
  - Black: `[tool.black]`
  - isort: `[tool.isort]`
  - Poetry: `[tool.poetry]`
  - Hatch: `[tool.hatch]`

Why use `pyproject.toml` in this repo?

- If you want to adopt a modern packaging workflow (publish a package, use Poetry/Hatch, or centralize tool config), add `pyproject.toml` and migrate configuration from other files.
- For a simple application repository that is not distributed as a package, `pyproject.toml` is optional but useful for consolidating tool config (black, isort) and enabling PEP 517 build isolation.

When not required:

- If you don't build/install the project as a package and prefer `requirements.txt`/venv workflows, `pyproject.toml` is not strictly required.

If you want, I can:

- Create a minimal `pyproject.toml` with tool configuration for `black`, `isort`, and `pytest` that matches the project's current dev tooling.
- Or create a Poetry-managed `pyproject.toml` and `poetry.lock` to manage dependencies instead of `requirements.txt`.

Tell me whether to add a minimal `pyproject.toml` (tool config only) or convert the project to Poetry/another build system.
