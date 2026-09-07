from bimanual.doctor import diagnose


def test_rosetta_is_rejected_before_native_library_imports(monkeypatch):
    monkeypatch.setattr("bimanual.doctor.platform.system", lambda: "Darwin")
    monkeypatch.setattr("bimanual.doctor.platform.machine", lambda: "x86_64")
    result = diagnose()
    assert result["outcome"] == "failed"
    assert result["native_runtime"] == "failed"
    assert "versions" not in result
