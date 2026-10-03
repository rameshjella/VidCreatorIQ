from pathlib import Path

from app.services.sfx_semantic_service import SFXSemanticMatcher


def test_semantic_matcher_prefers_related_asset(tmp_path: Path) -> None:
    ocean = tmp_path / "ocean_waves_heavy.wav"
    city = tmp_path / "busy_city_traffic.wav"
    ocean.write_bytes(b"fake")
    city.write_bytes(b"fake")

    matcher = SFXSemanticMatcher(dims=128)
    matcher.index_library(tmp_path)

    result = matcher.search("A stormy sea with crashing waves", top_k=1)
    assert result, "Expected at least one match"
    assert "ocean" in result[0].path.stem

