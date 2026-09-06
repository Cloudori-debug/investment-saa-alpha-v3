"""FTC circular ownership via data.go.kr REST — no HTML scrape."""

from __future__ import annotations

from pathlib import Path

from alpha_system.sizing.hakedaka_screen import evaluate_hakedaka, load_hakedaka_inputs
from src.data_refresh.ftc_circular import (
    GROUP_PATH,
    ROTAT_PATH,
    FtcApiError,
    ftc_get,
    map_names_to_tickers,
    normalize_corp_name,
    normalize_service_key,
    parse_items_xml,
    refresh_ftc_circular,
)


def _xml(body: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
  <body>{body}</body>
</response>""".encode("utf-8")


def test_normalize_service_key_unquotes_encoding_key() -> None:
    raw = "abcd+/ef=="
    encoded = "abcd%2B%2Fef%3D%3D"
    assert normalize_service_key(encoded) == raw
    assert normalize_service_key(raw) == raw
    assert normalize_service_key("abcd%252B") == "abcd+"


def test_ftc_get_does_not_double_encode_service_key() -> None:
    seen: list[str] = []

    def get_url(url: str) -> bytes:
        seen.append(url)
        return (
            b'<?xml version="1.0"?><response><header>'
            b"<resultCode>00</resultCode><resultMsg>OK</resultMsg>"
            b"</header><body><totalCount>0</totalCount><items></items></body></response>"
        )

    ftc_get(
        ROTAT_PATH,
        {"pageNo": 1, "numOfRows": 1},
        api_key="ab+c%3D",
        get_url=get_url,
    )
    assert seen
    assert "serviceKey=ab%2Bc%3D" in seen[0]
    assert "%253D" not in seen[0]


def test_normalize_and_map_names() -> None:
    assert normalize_corp_name("삼성전자(주)") == "삼성전자"
    assert normalize_corp_name("주식회사 현대모비스") == "현대모비스"
    hit, miss = map_names_to_tickers(
        ["삼성전자(주)", "없는회사", "현대자동차"],
        {"삼성전자": "005930", "현대차": "005380"},
    )
    assert hit == ["005930", "005380"]
    assert miss == ["없는회사"]


def test_parse_native_ftc_list_xml() -> None:
    raw = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<grupRotatInvstmntList>"
        "<resultCode>00</resultCode><resultMsg>SUCCESS</resultMsg>"
        "<totalCount>1</totalCount>"
        "<grupRotatInvstmnt>"
        "<unityGrupNm>현대자동차</unityGrupNm>"
        "<rotatInvstmntLoopCo>4</rotatInvstmntLoopCo>"
        "</grupRotatInvstmnt>"
        "</grupRotatInvstmntList>"
    ).encode("utf-8")
    code, msg, total, items = parse_items_xml(raw)
    assert code == "00"
    assert msg == "SUCCESS"
    assert total == 1
    assert items[0]["unityGrupNm"] == "현대자동차"
    assert items[0]["rotatInvstmntLoopCo"] == "4"


def test_parse_rotat_xml() -> None:
    raw = _xml(
        """
    <totalCount>1</totalCount>
    <items>
      <item>
        <unityGrupNm>현대자동차</unityGrupNm>
        <rotatInvstmntLoopCo>2</rotatInvstmntLoopCo>
      </item>
    </items>
    """
    )
    code, msg, total, items = parse_items_xml(raw)
    assert code == "00"
    assert msg == "OK"
    assert total == 1
    assert items[0]["unityGrupNm"] == "현대자동차"
    assert items[0]["rotatInvstmntLoopCo"] == "2"


def test_refresh_maps_representative_and_caches(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe.csv").write_text(
        "ticker,name\n005380,현대차\n012330,현대모비스\n",
        encoding="utf-8",
    )

    def get_url(url: str) -> bytes:
        if ROTAT_PATH in url:
            return _xml(
                """
            <totalCount>1</totalCount>
            <items>
              <item>
                <unityGrupNm>현대자동차</unityGrupNm>
                <rotatInvstmntLoopCo>2</rotatInvstmntLoopCo>
              </item>
            </items>
            """
            )
        if GROUP_PATH in url:
            return _xml(
                """
            <totalCount>1</totalCount>
            <items>
              <item>
                <unityGrupNm>현대자동차</unityGrupNm>
                <unityGrupCode>K1000032</unityGrupCode>
                <repreCmpny>현대차</repreCmpny>
              </item>
            </items>
            """
            )
        return _xml("<totalCount>0</totalCount><items></items>")

    result = refresh_ftc_circular(
        tmp_path,
        api_key="dummy-key",
        get_url=get_url,
    )
    assert result.ok is True
    assert "005380" in result.tickers
    cache = tmp_path / "data" / "cache" / "ftc_circular.json"
    assert cache.exists()

    inputs = load_hakedaka_inputs(tmp_path, data_dir=tmp_path / "data")
    assert inputs.circular_flag.get("005380") is True
    verdict = evaluate_hakedaka("005380", inputs, min_hits=1)
    assert verdict.circular is True
    assert verdict.passed is True
    # Unlisted names stay fail-open, not a known miss.
    other = evaluate_hakedaka("100840", inputs, min_hits=2)
    assert other.circular is None
    assert other.passed is True


def test_refresh_survives_group_api_403(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe.csv").write_text(
        "ticker,name\n005380,현대차\n",
        encoding="utf-8",
    )

    def get_url(url: str) -> bytes:
        if GROUP_PATH in url:
            raise FtcApiError("FTC HTTP 403")
        if ROTAT_PATH in url:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<grupRotatInvstmntList>"
                "<resultCode>00</resultCode><resultMsg>SUCCESS</resultMsg>"
                "<totalCount>1</totalCount>"
                "<grupRotatInvstmnt>"
                "<unityGrupNm>현대자동차</unityGrupNm>"
                "<rotatInvstmntLoopCo>4</rotatInvstmntLoopCo>"
                "</grupRotatInvstmnt>"
                "</grupRotatInvstmntList>"
            ).encode("utf-8")
        return _xml("<totalCount>0</totalCount><items></items>")

    result = refresh_ftc_circular(tmp_path, api_key="dummy-key", get_url=get_url)
    assert result.ok is True
    assert "005380" in result.tickers
    assert "지정집단 API 생략" in result.detail


def test_missing_key_fail_open(tmp_path: Path) -> None:
    result = refresh_ftc_circular(tmp_path, api_key="")
    assert result.ok is False
    assert not (tmp_path / "data" / "cache" / "ftc_circular.json").exists()
