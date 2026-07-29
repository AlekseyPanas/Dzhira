"""The value type flowing through the derived-dict core.

A node is genuinely heterogeneous (scalar / list / nested dict, arbitrarily deep) — honestly
``Any``. Aliasing it lets every signature in the pub/sub core, the tree helpers and the folder
mirror visibly refer to the SAME thing. (Ported from eventCamera's ``node_types.py``.)
"""

from typing import Any

TNodeValue = Any
