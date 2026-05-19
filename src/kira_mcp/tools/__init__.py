"""Importing this package registers all tools on the shared FastMCP instance.

Each submodule decorates functions with `@mcp.tool()` from `kira_mcp._mcp`,
so a bare `from . import tools` is enough to wire them up.

`omniparser` is intentionally NOT imported here — it requires REPLICATE_API_TOKEN
and a network call. The implementation lives in `omniparser.py`; uncomment the
import below to enable it.
"""

from . import contour  # noqa: F401
from . import mouse  # noqa: F401
from . import keyboard  # noqa: F401
from . import screen  # noqa: F401
from . import clipboard  # noqa: F401
# from . import omniparser  # noqa: F401  # enable once REPLICATE_API_TOKEN is set
