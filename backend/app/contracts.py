"""Import shared Python contracts from the repository-level contracts package.

`contracts/contracts.py` is the single Pydantic source for Modules 2–4.
The root directory is on `sys.path` in Compose via `/app/contracts`; for host
runs, add the repository root explicitly when needed.
"""

try:
    from contracts.contracts import *  # noqa: F401,F403
except ModuleNotFoundError as exc:
    if exc.name != "contracts":
        raise
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from contracts.contracts import *  # noqa: F401,F403
