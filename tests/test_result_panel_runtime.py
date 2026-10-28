"""Exercise real Tcl/Tk ownership on Windows without showing windows or using the clipboard."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Tcl/Tk regression")
def test_nonblocking_panel_updates_closes_and_reopens_on_its_tk_thread():
    script = textwrap.dedent("""
        import json
        import threading
        import time
        import tkinter as tk
        import roascan.desktop.result_panel as rp

        observed = []
        created_on = []
        ran_on = []
        errors = []
        threading.excepthook = lambda args: errors.append(str(args.exc_value))
        original_tk = tk.Tk
        original_run = rp.ResultPanelWindow.run

        def hidden_tk(*args, **kwargs):
            root = original_tk(*args, **kwargs)
            root.withdraw()
            created_on.append(threading.get_ident())
            def observe():
                panel = rp._active_panel_instance
                if panel is not None:
                    observed.append(panel.get_current_text())
                root.after(20, observe)
            root.after(20, observe)
            return root

        def tracked_run(panel):
            ran_on.append(threading.get_ident())
            return original_run(panel)

        tk.Tk = hidden_tk
        rp.ResultPanelWindow.run = tracked_run
        rp.ResultPanelWindow.bring_to_front = lambda self: None

        for cycle in range(2):
            first = rp.show_result_panel("first", blocking=False)
            second = rp.show_result_panel(f"updated {cycle}", blocking=False)
            assert first is second
            deadline = time.monotonic() + 2
            while f"updated {cycle}" not in observed and time.monotonic() < deadline:
                time.sleep(.02)
            second.update_content(f"edited {cycle}")
            deadline = time.monotonic() + 2
            while f"edited {cycle}" not in observed and time.monotonic() < deadline:
                time.sleep(.02)
            second.close()

        print(json.dumps({"created_on": created_on, "ran_on": ran_on,
                          "observed": observed, "errors": errors,
                          "closed": rp._active_panel_instance is None}))
    """)
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, ROASCAN_CONFIG_PATH=str(root / ".unused-test-config.json"))
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=root, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout.splitlines()[-1])
    assert state["errors"] == [], state
    assert state["created_on"] == state["ran_on"], state
    assert "updated 0" in state["observed"], state
    assert "updated 1" in state["observed"], state
    assert "edited 0" in state["observed"], state
    assert "edited 1" in state["observed"], state
    assert state["closed"], state


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Tcl/Tk regression")
def test_blocking_panel_waits_for_its_window_to_close():
    script = textwrap.dedent("""
        import json
        import tkinter as tk
        import roascan.desktop.result_panel as rp

        original_tk = tk.Tk
        def hidden_tk(*args, **kwargs):
            root = original_tk(*args, **kwargs)
            root.withdraw()
            root.after(100, rp.close_active_panel)
            return root
        tk.Tk = hidden_tk
        rp.ResultPanelWindow.bring_to_front = lambda self: None
        panel = rp.show_result_panel("blocking OCR", blocking=True)
        print(json.dumps({"closed": panel.root is None,
                          "singleton_released": rp._active_panel_instance is None}))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parent.parent,
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {
        "closed": True, "singleton_released": True,
    }
