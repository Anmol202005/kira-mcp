"""The shared FastMCP instance. Tool modules import `mcp` from here and decorate
their functions with `@mcp.tool()` — importing `kira_mcp.tools` triggers all
registrations via side effects."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kira-mcp")
