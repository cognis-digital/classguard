"""CLASSGUARD MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from classguard.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-classguard[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-classguard[mcp]'")
        return 1
    app = FastMCP("classguard")

    @app.tool()
    def classguard_scan(target: str) -> str:
        """Validate classification banner markings (CUI/CONFIDENTIAL/SECRET) in documents per portion-marking rules.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
