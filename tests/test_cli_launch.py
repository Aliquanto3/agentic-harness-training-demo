from __future__ import annotations

from wavestack import cli


def test_reserve_port_then_conflict_returns_none_for_second_caller():
    first = cli._try_reserve_port(0)  # port 0: OS picks a free ephemeral port
    assert first is not None
    port = first.getsockname()[1]
    try:
        second = cli._try_reserve_port(port)
        assert second is None
    finally:
        first.close()


def test_main_opens_browser_and_exits_zero_when_existing_instance_healthy(monkeypatch):
    opened = []
    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: None)
    monkeypatch.setattr(cli, "_existing_instance_healthy", lambda port: True)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))

    exit_code = cli.main(["--port", "8888"])

    assert exit_code == 0
    assert opened == ["http://127.0.0.1:8888/diagnostic"]


def test_main_reports_conflict_and_exits_nonzero_when_port_used_by_other_process(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_try_reserve_port", lambda port: None)
    monkeypatch.setattr(cli, "_existing_instance_healthy", lambda port: False)

    exit_code = cli.main(["--port", "8888"])

    assert exit_code == 1
    assert "8888" in capsys.readouterr().out
