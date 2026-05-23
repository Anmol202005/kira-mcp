"""Importing this package registers all tools on the shared FastMCP instance.

Each submodule decorates functions with `@mcp.tool()` from `kira_mcp._mcp`,
so a bare `from . import tools` is enough to wire them up.

`screen` is imported before `parse` because `parse` uses the `Region` model
defined in `screen`.
"""

from . import screen  # noqa: F401
from . import parse  # noqa: F401
from . import mouse  # noqa: F401
from . import keyboard  # noqa: F401
from . import clipboard  # noqa: F401
