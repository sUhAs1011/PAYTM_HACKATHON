"""Re-export contracts for seamless module resolution within backend package."""
try:
    from contracts.contracts import *
except ImportError:
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from contracts.contracts import *

