"""CLASSGUARD MCP server — exposes classguard_scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
import json
from classguard.core import analyze_document, analyze_text


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-classguard[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("Install the MCP extra: pip install 'cognis-classguard[mcp]'")
        return 1
    app = FastMCP("classguard")

    @app.tool()
    def classguard_scan(target: str) -> str:
        """Validate classification banner markings (CUI/CONFIDENTIAL/SECRET) in a
        document per portion-marking rules.  *target* may be a file path or raw text.
        Returns JSON findings."""
        if not isinstance(target, str) or not target.strip():
            return json.dumps({"error": "target must be a non-empty string"})
        try:
            import os
            if os.path.exists(target):
                report = analyze_document(target)
            else:
                report = analyze_text(target, source="<mcp-input>")
            return json.dumps(report.to_dict(), indent=2)
        except OSError as exc:
            return json.dumps({"error": "cannot read file: %s" % exc})
        except Exception as exc:
            return json.dumps({"error": "analysis failed: %s" % exc})

    app.run()
    return 0
