"""
Second Brain — Plugin Loader
==============================
Dynamically discovers and loads external plugins (tools) 
from the 'plugins/' directory at runtime.
"""

import os
import sys
import logging
import importlib.util
import inspect
from pathlib import Path

from config.settings import PLUGINS_DIR
from src.tools.base import BaseTool
from src.tools.registry import register_tool

logger = logging.getLogger(__name__)

def load_all_plugins() -> None:
    """
    Scans the plugins directory, imports all valid python files,
    finds classes that inherit from BaseTool (but are not BaseTool itself),
    and registers them in the global tool registry.
    """
    if not PLUGINS_DIR.exists():
        logger.info(f"Plugins directory not found at {PLUGINS_DIR}. Creating it...")
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        return

    # Add PLUGINS_DIR to sys.path so plugins can import other modules easily if needed
    if str(PLUGINS_DIR) not in sys.path:
        sys.path.insert(0, str(PLUGINS_DIR))

    plugin_files = [f for f in PLUGINS_DIR.iterdir() if f.is_file() and f.suffix == ".py" and not f.name.startswith("__")]

    loaded_count = 0

    for file_path in plugin_files:
        module_name = f"plugins.{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Inspect module for BaseTool subclasses
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        # Instantiate the tool and register it
                        tool_instance = obj()
                        register_tool(tool_instance)
                        loaded_count += 1
                        logger.debug(f"Loaded plugin tool: {tool_instance.name} from {file_path.name}")
        except Exception as e:
            logger.error(f"Failed to load plugin from {file_path.name}: {e}")

    if loaded_count > 0:
        logger.info(f"Successfully loaded {loaded_count} plugin(s) from {PLUGINS_DIR}")
    else:
        logger.info("No external plugins loaded.")
