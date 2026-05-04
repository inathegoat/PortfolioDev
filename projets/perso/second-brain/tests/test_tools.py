"""
Tests for Phase 5+6 — Tool System & Safety Layer
====================================================
Tests tool registration, execution, safety controls,
path sandboxing, audit logging, and LLM routing.
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
#  TEST 1: Tool Registration
# ═══════════════════════════════════════════════════════════════════

def test_registration():
    """Test tool registration and discovery."""
    from src.tools.registry import (
        register_tool, get_tool, list_tools,
        get_tool_names, clear_registry,
    )
    from src.tools.base import BaseTool, PERMISSION_SAFE_WRITE

    clear_registry()

    # Create a test tool
    class DummyTool(BaseTool):
        name = "dummy_test"
        description = "A test tool"
        permission_level = PERMISSION_SAFE_WRITE

        def schema(self):
            return {
                "message": {
                    "type": "string",
                    "required": True,
                    "description": "Test message",
                },
            }

        def execute(self, message="", **kwargs):
            return {"status": "success", "message": f"Got: {message}"}

    # Register
    tool = DummyTool()
    register_tool(tool)

    assert "dummy_test" in get_tool_names()
    print("✅ Test 1.1: Tool registration — PASSED")

    assert get_tool("dummy_test") is not None
    print("✅ Test 1.2: Tool lookup — PASSED")

    tools = list_tools()
    assert len(tools) >= 1
    assert tools[0]["name"] == "dummy_test"
    print(f"✅ Test 1.3: Tool listing — PASSED ({len(tools)} tools)")

    clear_registry()


def test_builtin_registration():
    """Test that all built-in tools register correctly."""
    from src.tools.registry import get_tool_names, clear_registry
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    names = get_tool_names()
    expected = {"create_note", "create_task", "update_task_status", "export_data"}
    assert expected.issubset(set(names)), f"Missing tools: {expected - set(names)}"
    print(f"✅ Test 1.4: Built-in registration — PASSED ({len(names)} tools: {names})")

    clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  TEST 2: Argument Validation
# ═══════════════════════════════════════════════════════════════════

def test_arg_validation():
    """Test schema-based argument validation."""
    from src.tools.base import BaseTool, PERMISSION_SAFE_WRITE

    class StrictTool(BaseTool):
        name = "strict"
        description = "Strict tool"
        permission_level = PERMISSION_SAFE_WRITE

        def schema(self):
            return {
                "title": {"type": "string", "required": True},
                "count": {"type": "int", "required": False},
            }

        def execute(self, **kwargs):
            return {"status": "success"}

    tool = StrictTool()

    # Valid args
    ok, msg = tool.validate_args({"title": "hello"})
    assert ok is True
    print("✅ Test 2.1: Valid args — PASSED")

    # Missing required
    ok, msg = tool.validate_args({})
    assert ok is False
    assert "requis" in msg.lower() or "title" in msg
    print(f"✅ Test 2.2: Missing required arg — PASSED (msg: {msg})")

    # Wrong type
    ok, msg = tool.validate_args({"title": 123})
    assert ok is False
    print(f"✅ Test 2.3: Wrong type — PASSED (msg: {msg})")

    # Unknown arg
    ok, msg = tool.validate_args({"title": "ok", "unknown_field": "x"})
    assert ok is False
    assert "inconnus" in msg.lower() or "unknown" in msg.lower()
    print(f"✅ Test 2.4: Unknown arg — PASSED (msg: {msg})")


# ═══════════════════════════════════════════════════════════════════
#  TEST 3: Tool Execution
# ═══════════════════════════════════════════════════════════════════

def test_create_note():
    """Test the create_note tool end-to-end."""
    from src.tools.registry import clear_registry, execute_tool
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_notes = Path(tmpdir)
        with patch("src.tools.builtin.NOTES_DIR", tmp_notes):
            result = execute_tool("create_note", {
                "title": "Test Note",
                "content": "Ceci est un test.",
            })

    assert result["status"] == "success"
    assert "Test Note" in result["message"]
    print(f"✅ Test 3.1: create_note — PASSED ({result['message']})")

    clear_registry()


def test_create_task():
    """Test the create_task tool."""
    from src.tools.registry import clear_registry, execute_tool
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)
        temp_path = Path(f.name)

    try:
        with patch("src.tasks.TASKS_FILE", temp_path), \
             patch("src.tasks.TASKS_DIR", temp_path.parent):
            result = execute_tool("create_task", {
                "title": "Tester le système d'outils",
                "description": "Vérifier que tout fonctionne",
                "priority": 7,
            })

        assert result["status"] == "success"
        assert "task_id" in result
        print(f"✅ Test 3.2: create_task — PASSED (id: {result['task_id']})")
    finally:
        temp_path.unlink(missing_ok=True)

    clear_registry()


def test_export_data():
    """Test the export_data tool."""
    from src.tools.registry import clear_registry, execute_tool
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exports = Path(tmpdir)
        with patch("src.tools.builtin.EXPORTS_DIR", tmp_exports):
            result = execute_tool("export_data", {
                "data_type": "goals",
            })

    assert result["status"] == "success"
    assert "items_exported" in result
    print(f"✅ Test 3.3: export_data — PASSED ({result['message']})")

    clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  TEST 4: Safety — Allowlist
# ═══════════════════════════════════════════════════════════════════

def test_unknown_tool():
    """Test that unknown tools are rejected."""
    from src.tools.registry import clear_registry, execute_tool
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    result = execute_tool("rm_rf_everything", {"path": "/"})
    assert result["status"] == "error"
    assert "inconnu" in result["message"].lower()
    print(f"✅ Test 4.1: Unknown tool blocked — PASSED")

    clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  TEST 5: Safety — Path Sandboxing
# ═══════════════════════════════════════════════════════════════════

def test_path_sandbox():
    """Test that paths outside allowed dirs are blocked."""
    from src.tools.registry import is_path_allowed
    from config.settings import NOTES_DIR

    # Allowed path
    assert is_path_allowed(str(NOTES_DIR / "test.md")) is True
    print("✅ Test 5.1: Allowed path — PASSED")

    # Blocked path
    assert is_path_allowed("/etc/passwd") is False
    print("✅ Test 5.2: Blocked path (/etc/passwd) — PASSED")

    assert is_path_allowed("/tmp/evil.sh") is False
    print("✅ Test 5.3: Blocked path (/tmp) — PASSED")

    # Relative traversal
    assert is_path_allowed(str(NOTES_DIR / "../../etc/passwd")) is False
    print("✅ Test 5.4: Path traversal blocked — PASSED")


# ═══════════════════════════════════════════════════════════════════
#  TEST 6: Safety — Permission Levels
# ═══════════════════════════════════════════════════════════════════

def test_restricted_permission():
    """Test that restricted tools require confirmation."""
    from src.tools.registry import clear_registry, register_tool, execute_tool
    from src.tools.base import BaseTool, PERMISSION_RESTRICTED

    clear_registry()

    class DangerousTool(BaseTool):
        name = "delete_everything"
        description = "Deletes all data"
        permission_level = PERMISSION_RESTRICTED

        def schema(self):
            return {}

        def execute(self, **kwargs):
            return {"status": "success", "message": "Deleted!"}

    register_tool(DangerousTool())

    # Without confirmation function → blocked
    result = execute_tool("delete_everything", {})
    assert result["status"] == "blocked"
    print(f"✅ Test 6.1: Restricted without confirm — BLOCKED")

    # With confirmation = False → cancelled
    result = execute_tool("delete_everything", {}, confirm_fn=lambda m: False)
    assert result["status"] == "cancelled"
    print(f"✅ Test 6.2: Restricted with deny — CANCELLED")

    # With confirmation = True → executed
    result = execute_tool("delete_everything", {}, confirm_fn=lambda m: True)
    assert result["status"] == "success"
    print(f"✅ Test 6.3: Restricted with confirm — EXECUTED")

    clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  TEST 7: Audit Log
# ═══════════════════════════════════════════════════════════════════

def test_audit_log():
    """Test that all tool executions are logged."""
    from src.tools.registry import (
        clear_registry, execute_tool,
        load_audit_log,
    )
    from src.tools.builtin import register_builtin_tools

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump([], f)
        temp_log = Path(f.name)

    try:
        with patch("src.tools.registry.TOOLS_LOG_FILE", temp_log), \
             patch("src.tools.registry.LOGS_DIR", temp_log.parent):
            clear_registry()
            register_builtin_tools()

            # Execute a tool (it may fail but should still be logged)
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch("src.tools.builtin.NOTES_DIR", Path(tmpdir)):
                    execute_tool("create_note", {
                        "title": "Audit Test",
                        "content": "Testing audit log.",
                    })

            # Execute an unknown tool (should also be logged)
            execute_tool("nonexistent", {})

            # Read log
            log_content = json.loads(temp_log.read_text(encoding="utf-8"))
            assert len(log_content) >= 2
            assert log_content[0]["tool"] == "create_note"
            assert log_content[1]["tool"] == "nonexistent"
            print(f"✅ Test 7.1: Audit log — PASSED ({len(log_content)} entries)")

    finally:
        temp_log.unlink(missing_ok=True)
        clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  TEST 8: LLM Router
# ═══════════════════════════════════════════════════════════════════

def test_router_parse():
    """Test parsing of LLM tool responses."""
    from src.tools.registry import clear_registry
    from src.tools.builtin import register_builtin_tools
    from src.tools.llm_router import _parse_tool_response

    clear_registry()
    register_builtin_tools()

    # Clean JSON
    result = _parse_tool_response(
        '{"tool": "create_note", "args": {"title": "Test", "content": "Hello"}}'
    )
    assert result is not None
    assert result["tool"] == "create_note"
    print("✅ Test 8.1: Clean JSON parsing — PASSED")

    # Null tool
    result = _parse_tool_response('{"tool": null}')
    assert result is not None
    assert result["tool"] is None
    print("✅ Test 8.2: Null tool parsing — PASSED")

    # JSON in markdown code block
    result = _parse_tool_response(
        '```json\n{"tool": "export_data", "args": {"data_type": "all"}}\n```'
    )
    assert result is not None
    assert result["tool"] == "export_data"
    print("✅ Test 8.3: Markdown code block parsing — PASSED")

    # Messy LLM output
    result = _parse_tool_response(
        'I think you should use this tool:\n'
        '{"tool": "create_task", "args": {"title": "Learn ML"}}\n'
        'This will help you.'
    )
    assert result is not None
    assert result["tool"] == "create_task"
    print("✅ Test 8.4: Messy output parsing — PASSED")

    # Unknown tool → None
    result = _parse_tool_response('{"tool": "hack_nasa", "args": {}}')
    assert result is None
    print("✅ Test 8.5: Unknown tool rejected — PASSED")

    clear_registry()


def test_router_full():
    """Test the full router with mocked LLM."""
    from src.tools.registry import clear_registry
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    mock_response = '{"tool": "create_note", "args": {"title": "Mon idée", "content": "Test de routage"}}'

    with patch("src.tools.llm_router.LLMClient") as MockLLM:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = mock_response
        MockLLM.return_value = mock_instance

        from src.tools.llm_router import route_query

        decision = route_query("Crée une note sur mon idée de projet")

        assert decision is not None
        assert decision["tool"] == "create_note"
        assert decision["args"]["title"] == "Mon idée"
        print(f"✅ Test 8.6: Full routing — PASSED (tool={decision['tool']})")

    clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  TEST 9: End-to-End Tool Pipeline
# ═══════════════════════════════════════════════════════════════════

def test_end_to_end():
    """Test complete pipeline: route → validate → execute → audit."""
    from src.tools.registry import clear_registry, load_audit_log
    from src.tools.builtin import register_builtin_tools

    clear_registry()
    register_builtin_tools()

    mock_response = '{"tool": "create_note", "args": {"title": "E2E Test", "content": "Pipeline complet"}}'

    with tempfile.TemporaryDirectory() as tmpdir, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:

        json.dump([], f)
        temp_log = Path(f.name)

        with patch("src.tools.llm_router.LLMClient") as MockLLM, \
             patch("src.tools.builtin.NOTES_DIR", Path(tmpdir)), \
             patch("src.tools.registry.TOOLS_LOG_FILE", temp_log), \
             patch("src.tools.registry.LOGS_DIR", Path(tmpdir)):

            mock_instance = MagicMock()
            mock_instance.generate.return_value = mock_response
            MockLLM.return_value = mock_instance

            from src.tools.llm_router import route_and_execute

            result = route_and_execute(
                "Prends une note sur le routage d'outils"
            )

            assert result is not None
            assert result["status"] == "success"
            print(f"✅ Test 9.1: E2E execution — PASSED ({result['message']})")

            # Verify file was created
            notes = list(Path(tmpdir).glob("*.md"))
            assert len(notes) >= 1
            print(f"✅ Test 9.2: File created — PASSED ({notes[0].name})")

            # Verify audit log
            log = json.loads(temp_log.read_text())
            assert len(log) >= 1
            assert log[-1]["result_status"] == "success"
            print(f"✅ Test 9.3: Audit logged — PASSED")

        temp_log.unlink(missing_ok=True)

    clear_registry()


# ═══════════════════════════════════════════════════════════════════
#  RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════

def run_all():
    """Run all Phase 5+6 tests."""
    print("=" * 60)
    print("  Phase 5+6 — Tool System & Safety Layer Tests")
    print("=" * 60)
    print()

    tests = [
        ("Tool Registration", test_registration),
        ("Built-in Registration", test_builtin_registration),
        ("Argument Validation", test_arg_validation),
        ("Create Note Tool", test_create_note),
        ("Create Task Tool", test_create_task),
        ("Export Data Tool", test_export_data),
        ("Unknown Tool (Allowlist)", test_unknown_tool),
        ("Path Sandboxing", test_path_sandbox),
        ("Restricted Permissions", test_restricted_permission),
        ("Audit Log", test_audit_log),
        ("Router: JSON Parsing", test_router_parse),
        ("Router: Full Routing", test_router_full),
        ("End-to-End Pipeline", test_end_to_end),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            print(f"\n── {name} ──")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {name} — FAILED: {e}")
            failed += 1
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
