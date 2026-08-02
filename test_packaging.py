from pathlib import Path


def test_release_build_collects_and_verifies_certifi_ca_bundle():
    script = (Path(__file__).parent / 'build_release.sh').read_text(encoding='utf-8')

    assert "collect_data_files('certifi')" in script
    assert 'Contents/Frameworks/certifi/cacert.pem' in script
    assert 'Build is missing the TLS certificate bundle' in script
    assert 'pgrep -f "$DESKTOP_EXECUTABLE"' in script
    assert 'Close it before replacing the desktop app' in script
