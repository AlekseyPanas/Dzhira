"""Dead-simple logging shim.

The ported derived-dict core (from eventCamera) calls ``warn(...)`` on the paths that must never
crash a worker thread (a bad subscriber, a malformed mid-write read). Dzhira has no logging service
to speak of — this is a parody — so ``warn`` just prints to stderr. Kept as its own tiny module so
every layer imports the SAME warn and we could swap in something richer later without touching them.
"""

import sys


def warn(message: str) -> None:
    print(f"[dzhira:warn] {message}", file=sys.stderr)
