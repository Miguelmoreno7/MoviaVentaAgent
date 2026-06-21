from pathlib import Path

from movia_sales_agent.config import paths


def test_project_root_resolves_to_workdir_when_package_is_installed(monkeypatch, tmp_path):
    app_root = tmp_path / "app"
    app_root.mkdir()
    (app_root / "platform_registry").mkdir()
    (app_root / "platform_registry" / "agents.json").write_text('{"agents":[]}', encoding="utf-8")
    fake_package_file = (
        tmp_path
        / "usr"
        / "local"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "movia_sales_agent"
        / "config"
        / "paths.py"
    )
    fake_package_file.parent.mkdir(parents=True)
    fake_package_file.write_text("", encoding="utf-8")

    monkeypatch.chdir(app_root)
    monkeypatch.setattr(paths, "__file__", str(fake_package_file))

    assert paths.resolve_project_root() == app_root


def test_project_root_falls_back_to_package_root(monkeypatch, tmp_path):
    fake_package_root = tmp_path / "repo"
    fake_package_file = fake_package_root / "src" / "movia_sales_agent" / "config" / "paths.py"
    fake_package_file.parent.mkdir(parents=True)
    fake_package_file.write_text("", encoding="utf-8")
    (fake_package_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()

    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.setattr(paths, "__file__", str(fake_package_file))

    assert paths.resolve_project_root() == fake_package_root
