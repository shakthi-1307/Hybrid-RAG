"""Worker entry point: ``python -m app.worker``.

A thin shim so the module path a human types stays short and stable while the
implementation lives with the rest of the job machinery.
"""

from __future__ import annotations

from app.jobs.worker import main

if __name__ == "__main__":
    main()
