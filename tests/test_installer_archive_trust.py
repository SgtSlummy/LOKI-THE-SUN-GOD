from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_loki_services.ps1"


def powershell() -> str:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    return shell


def make_untrusted_candidate(tmp_path: Path) -> dict[str, Path | str]:
    release = tmp_path / "release"
    scripts = release / "scripts"
    scripts.mkdir(parents=True)
    marker = tmp_path / "candidate-code-ran.txt"
    (scripts / "release_manifest.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('candidate code ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    archive = tmp_path / "candidate.zip"
    archive.write_bytes(b"operator-reviewed archive bytes")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar = Path(f"{archive}.sha256.json")
    sidecar.write_text(
        json.dumps(
            {
                "schema": "loki-release-archive-digest/v1",
                "candidate_id": "loki-test",
                "commit_id": "1" * 40,
                "tree_id": "2" * 40,
                "archive_name": archive.name,
                "archive_sha256": digest,
                "archive_size": archive.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    return {
        "release": release,
        "archive": archive,
        "sidecar": sidecar,
        "marker": marker,
        "digest": digest,
    }


def run_installer(
    fixture: dict[str, Path | str], *extra: str, evidence_only: bool = True
) -> subprocess.CompletedProcess[str]:
    mode = ["-EvidenceOnly"] if evidence_only else []
    return subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALLER),
            "-ReleaseRoot",
            str(fixture["release"]),
            "-ArchivePath",
            str(fixture["archive"]),
            "-SidecarPath",
            str(fixture["sidecar"]),
            "-TrustedPythonLauncher",
            r"C:\Windows\py.exe",
            "-TrustedPythonRuntime",
            r"C:\Program Files\Python312\python.exe",
            "-TrustedGitExecutable",
            r"C:\Program Files\Git\cmd\git.exe",
            *mode,
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_trusted_digest_is_mandatory_and_precedes_candidate_execution(tmp_path):
    fixture = make_untrusted_candidate(tmp_path)

    result = run_installer(fixture)

    assert result.returncode != 0
    assert "ExpectedArchiveSha256" in output_of(result)
    assert not Path(fixture["marker"]).exists()


def test_trusted_digest_rejects_invalid_shape_before_candidate_execution(tmp_path):
    fixture = make_untrusted_candidate(tmp_path)

    result = run_installer(fixture, "-ExpectedArchiveSha256", "not-a-sha256")

    assert result.returncode != 0
    assert "ExpectedArchiveSha256 must be exactly 64 hexadecimal characters" in output_of(result)
    assert not Path(fixture["marker"]).exists()


def test_trusted_digest_rejects_archive_mismatch_before_candidate_execution(tmp_path):
    fixture = make_untrusted_candidate(tmp_path)
    wrong_digest = "0" * 64

    result = run_installer(fixture, "-ExpectedArchiveSha256", wrong_digest)

    assert result.returncode != 0
    assert "Trusted archive SHA-256 mismatch" in output_of(result)
    assert not Path(fixture["marker"]).exists()


def test_trusted_digest_rejects_sidecar_mismatch_before_candidate_execution(tmp_path):
    fixture = make_untrusted_candidate(tmp_path)
    sidecar = json.loads(Path(fixture["sidecar"]).read_text(encoding="utf-8"))
    sidecar["archive_sha256"] = "f" * 64
    Path(fixture["sidecar"]).write_text(json.dumps(sidecar), encoding="utf-8")

    result = run_installer(fixture, "-ExpectedArchiveSha256", str(fixture["digest"]).upper())

    assert result.returncode != 0
    assert "Trusted sidecar SHA-256 mismatch" in output_of(result)
    assert not Path(fixture["marker"]).exists()


def test_service_installer_refuses_direct_nonbootstrap_execution(tmp_path):
    fixture = make_untrusted_candidate(tmp_path)

    result = run_installer(
        fixture,
        "-ExpectedArchiveSha256",
        str(fixture["digest"]),
        evidence_only=False,
    )

    assert result.returncode != 0
    assert "only through the protected external bootstrap" in output_of(result)
    assert not Path(fixture["marker"]).exists()


def test_trusted_digest_comparison_is_before_python_or_manifest_helper():
    source = INSTALLER.read_text(encoding="utf-8")
    expected_comparison = source.index("Trusted archive SHA-256 mismatch")
    sidecar_comparison = source.index("Trusted sidecar SHA-256 mismatch")
    python_lookup = source.index("$runtimeVersion = Invoke-NativeText")
    manifest_helper = source.index('$trustedManifestHelper = Join-Path $bootstrapRoot "release_manifest.py"')

    assert expected_comparison < python_lookup
    assert sidecar_comparison < python_lookup
    assert expected_comparison < manifest_helper
    assert sidecar_comparison < manifest_helper


def test_trusted_archive_helper_bootstraps_release_verification():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "System.IO.Compression.ZipFile" in source
    assert '$trustedManifestHelper = Join-Path $bootstrapRoot "release_manifest.py"' in source
    assert '$manifestHelper = Join-Path $ReleaseRoot "scripts\\release_manifest.py"' not in source
    assert '"-I", "-B", $trustedManifestHelper' in source
    directory_check = source.index('"verify-directory", "--root", $ReleaseRoot')
    candidate_execution = source.index(
        '"-File", (Join-Path $ReleaseRoot "scripts\\install_loki_local.ps1")'
    )
    assert directory_check < candidate_execution


def test_service_installer_has_read_only_evidence_mode_and_staged_path_gate():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "[switch]$EvidenceOnly" in source
    assert "function Assert-StagedInstallerInvocation" in source
    assert '^run-[0-9a-f]{32}$' in source
    assert "only through the protected external bootstrap" in source
    assert "if ($EvidenceOnly)" in source
    assert "$stagedInstallerRunRoot = Assert-StagedInstallerInvocation" in source
    assert 'Join-Path $stagedInstallerRunRoot ("inner-trust-"' in source
    assert "GetTempPath" not in source


def test_trusted_archive_and_sidecar_are_locked_then_copied_before_use():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "$archiveTrustStream" in source
    assert "$sidecarTrustStream" in source
    assert "[System.IO.FileShare]::None" in source
    assert '$trustedArchivePath = Join-Path $bootstrapRoot $archiveFile.Name' in source
    assert '$trustedSidecarPath = "$trustedArchivePath.sha256.json"' in source
    assert "Copy-LockedEvidenceFile" in source
    assert "Get-Sha256Hex -Stream $archiveTrustStream" in source
    assert "Get-Sha256Hex -Path $trustedArchivePath" in source
    assert "Copy-TrustedManifestHelper -Archive $trustedArchivePath" in source
    assert '"verify-archive", "--archive", $trustedArchivePath, "--sidecar", $trustedSidecarPath' in source
    assert source.index("Get-Sha256Hex -Path $trustedArchivePath") < source.index(
        "Copy-TrustedManifestHelper -Archive $trustedArchivePath"
    )
    assert source.count("$archiveTrustStream.Dispose()") == 1
    assert source.count("$sidecarTrustStream.Dispose()") == 1
