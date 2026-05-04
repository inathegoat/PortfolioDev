"""
Second Brain — Tool System (Phase 5+6)
========================================
Extensible tool framework with safety controls.
"""

def init_all_tools():
    """Initialize built-in tools and load external plugins."""
    from src.tools.registry import get_tool_names
    if not get_tool_names():
        from src.tools.builtin import register_builtin_tools
        from src.tools.plugin_loader import load_all_plugins
        register_builtin_tools()
        load_all_plugins()
