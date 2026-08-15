from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

import pytest

from scripts import release_manifest, scan_service_logs, windows_service_common


@pytest.mark.parametrize(
    "name",
    (
        "CONIN$",
        "CONOUT$",
        "COM¹",
        "COM².txt",
        "COM³.tar.gz",
        "LPT¹",
        "LPT².txt",
        "LPT³.tar.gz",
    ),
)
def test_release_paths_reject_all_windows_device_aliases(name):
    with pytest.raises(release_manifest.ManifestError, match="Windows archive path"):
        release_manifest._safe_relative_path(name)


def test_directory_verification_invokes_alternate_stream_check(tmp_path, monkeypatch):
    root = tmp_path / "release"
    root.mkdir()
    manifest = {
        "schema": release_manifest.SCHEMA,
        "candidate_id": "loki-test",
        "commit_id": "a" * 40,
        "tree_id": "b" * 40,
        "files": [],
    }
    (root / release_manifest.MANIFEST_NAME).write_text(
        __import__("json").dumps(manifest), encoding="utf-8"
    )

    def reject_streams(_root):
        raise release_manifest.ManifestError("alternate data stream detected")

    monkeypatch.setattr(
        release_manifest,
        "_assert_no_alternate_data_streams",
        reject_streams,
        raising=False,
    )

    with pytest.raises(release_manifest.ManifestError, match="alternate data stream"):
        release_manifest.verify_directory(root)


@pytest.mark.skipif(os.name != "nt", reason="NTFS alternate streams are Windows-only")
def test_alternate_stream_enumerator_rejects_hidden_stream(tmp_path):
    payload = tmp_path / "payload.py"
    payload.write_text("print('safe')\n", encoding="utf-8")
    try:
        Path(f"{payload}:hidden").write_text("hidden", encoding="utf-8")
    except OSError as error:
        pytest.skip(f"filesystem does not support alternate streams: {type(error).__name__}")

    with pytest.raises(release_manifest.ManifestError, match="alternate data stream"):
        release_manifest._assert_no_alternate_data_streams(tmp_path)


def _disable_real_credentials(monkeypatch):
    monkeypatch.setattr(scan_service_logs.credential_store, "read_credential", lambda _name: None)


def test_log_scan_includes_unlisted_secret_bearing_config_keys(tmp_path, monkeypatch):
    _disable_real_credentials(monkeypatch)
    secret = "unlisted-service-token-value"
    env_path = tmp_path / "runtime.env"
    env_path.write_text(f"UNLISTED_SERVICE_TOKEN={secret}\n", encoding="utf-8")
    log_path = tmp_path / "service.log"
    log_path.write_text(f"leak={secret}\n", encoding="utf-8")

    missing, credential_hits, pattern_hits = scan_service_logs.scan_logs([log_path], env_path)

    assert missing == []
    assert credential_hits == ["UNLISTED_SERVICE_TOKEN"]
    assert pattern_hits == []


def test_log_scan_detects_encoded_process_environment_secret(tmp_path, monkeypatch):
    _disable_real_credentials(monkeypatch)
    monkeypatch.setenv("CUSTOM_PASSWORD", "spaces and/slashes+")
    log_path = tmp_path / "service.log"
    log_path.write_text("spaces+and%2Fslashes%2B", encoding="utf-8")

    _missing, credential_hits, _pattern_hits = scan_service_logs.scan_logs([log_path])

    assert credential_hits == ["CUSTOM_PASSWORD"]


@pytest.mark.parametrize(
    "content",
    (
        '{"access_token":"value"}',
        "client_secret=value&scope=identify",
        "code=value&state=opaque",
        "Authorization: Bot value",
        "%22refresh_token%22%3A%22value%22",
    ),
)
def test_log_scan_detects_common_oauth_credential_shapes(tmp_path, monkeypatch, content):
    _disable_real_credentials(monkeypatch)
    log_path = tmp_path / "service.log"
    log_path.write_text(content, encoding="utf-8")

    _missing, _credential_hits, pattern_hits = scan_service_logs.scan_logs([log_path])

    assert pattern_hits


def test_log_scan_does_not_treat_unrelated_error_code_as_oauth(tmp_path, monkeypatch):
    _disable_real_credentials(monkeypatch)
    log_path = tmp_path / "service.log"
    log_path.write_text("error_code=500", encoding="utf-8")

    _missing, _credential_hits, pattern_hits = scan_service_logs.scan_logs([log_path])

    assert pattern_hits == []


def test_duplicate_matcher_rejects_same_basename_outside_managed_releases():
    command = [r"C:\other\python.exe", r"C:\attacker\dashboard_app.py"]

    assert not windows_service_common._command_is_service_child(
        command,
        "dashboard_app.py",
        expected_script=PureWindowsPath(r"C:\ProgramData\Loki\releases\active\dashboard_app.py"),
        managed_release_bases=(PureWindowsPath(r"C:\ProgramData\Loki\releases"),),
    )


def test_duplicate_matcher_accepts_other_versioned_managed_release():
    command = [
        r"C:\ProgramData\Loki\venvs\loki-old\Scripts\python.exe",
        r"C:\ProgramData\Loki\releases\loki-old\dashboard_app.py",
    ]

    assert windows_service_common._command_is_service_child(
        command,
        "dashboard_app.py",
        expected_script=PureWindowsPath(r"C:\ProgramData\Loki\releases\active\dashboard_app.py"),
        managed_release_bases=(PureWindowsPath(r"C:\ProgramData\Loki\releases"),),
    )
