"""
Tests for the CLI entrypoint (__main__).

The load -> context -> export/test flow lives in
``openrct2_object_common.dispatch`` (tested there); here we check this
generator's dispatch table and that ``main`` wires it into the shared CLI.
"""

from openrct2_scenery_generator import __main__ as cli


def test_real_dispatch_table_covers_every_object_type():
    assert set(cli._DISPATCH) == {
        "scenery_small",
        "scenery_large",
        "scenery_wall",
        "footpath_banner",
        "footpath_item",
        "scenery_group",
    }
    for triple in cli._DISPATCH.values():
        assert len(triple) == 3  # (load, export, export_test)


def test_main_delegates_to_run_dispatch_cli(monkeypatch):
    captured = {}

    def fake_run_dispatch_cli(prog, argv, dispatch, object_type_of):
        captured.update(
            prog=prog, argv=argv, dispatch=dispatch, object_type_of=object_type_of
        )
        return 0

    monkeypatch.setattr(cli, "run_dispatch_cli", fake_run_dispatch_cli)
    assert cli.main(["s.json"]) == 0
    assert captured["prog"] == "openrct2-scenery-generator"
    assert captured["argv"] == ["s.json"]
    assert captured["dispatch"] is cli._DISPATCH
    assert captured["object_type_of"] is cli.object_type_of


def test_main_returns_run_dispatch_cli_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_dispatch_cli", lambda *a, **k: 1)
    assert cli.main([]) == 1


def test_dunder_main_guard_invokes_sys_exit(monkeypatch):
    import runpy
    import sys

    exits = []
    monkeypatch.setattr(sys, "exit", exits.append)

    import openrct2_object_common.dispatch as _dispatch
    monkeypatch.setattr(_dispatch, "run_cli", lambda prog, argv, render: 5)

    sys.modules.pop("openrct2_scenery_generator.__main__", None)
    runpy.run_module("openrct2_scenery_generator", run_name="__main__")

    assert exits == [5]
