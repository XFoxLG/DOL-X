"""Sprite layout probe tests (drawImage geometry + baseline drift)."""

import json

import pytest

from tools.sprite_layout_probe import (
    CANVAS_GRID_PROFILE,
    DRAW_IMAGE_RECORDER,
    MAX_NETWORK_RECORDS,
    SPRITE_LOG_DUMP,
    SPRITE_LOG_RESET,
    _record_network,
    _layout_session,
    baseline_payload,
    build_summary,
    classify_network_failure,
    compare_sprite_layouts,
    grid_delta,
    highlight_assets,
    is_animated_layer,
    merge_asset_records,
    normalize_rect,
    parse_args,
    relativize_src,
    write_report,
)


def test_layout_session_is_a_context_manager():
    # Regression guard: a bare generator fails at ``with`` with
    # "generator object does not support the context manager protocol".
    assert hasattr(_layout_session, "__wrapped__")


def _asset(src, rects=None, count=1):
    return {"src": src, "count": count, "rects": list(rects or [])}


def _sample(sample_id, sprites, *, grid=None, opaque=100):
    return {
        "id": sample_id,
        "sprites": sprites,
        "pet_canvas": {"opaque": opaque, "grid": grid},
    }


def _rect(dx, dy, dw, dh, w=256, h=256):
    return {
        "dx": dx,
        "dy": dy,
        "dw": dw,
        "dh": dh,
        "canvasW": w,
        "canvasH": h,
    }


# --------------------------------------------------------------------------- #
# Injected scripts
# --------------------------------------------------------------------------- #


def test_draw_image_recorder_installs_a_guarded_hook():
    assert "CanvasRenderingContext2D" in DRAW_IMAGE_RECORDER
    assert "__DOLX_SPRITE_LOG" in DRAW_IMAGE_RECORDER
    assert "drawImage" in DRAW_IMAGE_RECORDER
    assert "__dolxSpriteRecorder" in DRAW_IMAGE_RECORDER
    # 3/5/9 argument forms must all be recorded.
    assert "args.length === 3" in DRAW_IMAGE_RECORDER
    assert "args.length === 5" in DRAW_IMAGE_RECORDER
    assert "args.length === 9" in DRAW_IMAGE_RECORDER


def test_five_argument_draw_image_is_recorded_as_a_destination_rect():
    # drawImage(image, dx, dy, dWidth, dHeight) must land in dx/dy/dw/dh -
    # mislabelling it as a source crop silently drops its position.
    five_arg_block = DRAW_IMAGE_RECORDER.split("args.length === 5")[1].split(
        "args.length === 9"
    )[0]
    assert "entry.dx = numberOrNull(args[1])" in five_arg_block
    assert "entry.dy = numberOrNull(args[2])" in five_arg_block
    assert "entry.dw = numberOrNull(args[3])" in five_arg_block
    assert "entry.dh = numberOrNull(args[4])" in five_arg_block
    assert "entry.sx" not in five_arg_block


def test_log_helpers_reset_and_dump_the_recorder():
    assert "__DOLX_SPRITE_LOG" in SPRITE_LOG_RESET
    assert "entries.length = 0" in SPRITE_LOG_RESET
    assert "__DOLX_SPRITE_LOG" in SPRITE_LOG_DUMP
    assert "distinct_sources" in SPRITE_LOG_DUMP


def test_canvas_grid_profile_reads_alpha_geometry():
    assert "getImageData" in CANVAS_GRID_PROFILE
    assert "centroid" in CANVAS_GRID_PROFILE
    assert "bbox" in CANVAS_GRID_PROFILE
    assert "grid" in CANVAS_GRID_PROFILE


# --------------------------------------------------------------------------- #
# URL / record merging
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://127.0.0.1:5555/img/face/default/blush-1.png", "img/face/default/blush-1.png"),
        ("https://example.test/img/ui/sym-awareness.png?v=2", "img/ui/sym-awareness.png"),
        ("/img/body/base-head.png", "img/body/base-head.png"),
        ("img/body/base-head.png", "img/body/base-head.png"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_relativize_src_strips_hosts_queries_and_leading_slashes(raw, expected):
    assert relativize_src(raw) == expected


def test_merge_asset_records_collapses_same_path_from_absolute_and_relative_urls():
    merged = merge_asset_records(
        [
            _asset("http://127.0.0.1:5555/img/face/blush-1.png", [_rect(10, 20, 30, 40)], 2),
            _asset("/img/face/blush-1.png", [_rect(11, 21, 31, 41)], 1),
        ]
    )
    assert len(merged) == 1
    assert merged[0]["src"] == "img/face/blush-1.png"
    assert merged[0]["count"] == 3
    assert len(merged[0]["rects"]) == 2


def test_merge_asset_records_keeps_key_layers_ahead_of_the_cap():
    records = [
        _asset(f"img/bg/filler-{index}.png", count=100 - index) for index in range(10)
    ]
    records.append(_asset("img/face/default/blush-3.png", count=1))
    merged = merge_asset_records(records, cap=3)
    assert len(merged) == 3
    assert merged[0]["src"] == "img/face/default/blush-3.png"


def test_merge_asset_records_is_empty_for_no_records():
    assert merge_asset_records([]) == []


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("img/face/default/blush1.png", "legacy_blush_tear_naming"),
        ("img/face/default/default/blush3.png", "legacy_blush_tear_naming"),
        ("img/face/default/tear2.png", "legacy_blush_tear_naming"),
        ("img/face/default/tears4.png", "legacy_blush_tear_naming"),
        # canonical dash names are not the legacy mismatch
        ("img/face/default/blush-1.png", None),
        ("img/face/default/tears-1.png", None),
        ("img/misc/banner.png", None),
    ],
)
def test_classify_network_failure_tags_legacy_face_naming(url, expected):
    assert classify_network_failure({"url": url}) == expected


# --------------------------------------------------------------------------- #
# Rect normalization
# --------------------------------------------------------------------------- #


def test_normalize_rect_converts_destination_to_canvas_coordinates():
    rect = _rect(64, 128, 32, 64)
    normalized = normalize_rect(rect)
    assert normalized == {
        "x": 0.25,
        "y": 0.5,
        "w": 0.125,
        "h": 0.25,
        "cx": 0.3125,
        "cy": 0.625,
    }


def test_normalize_rect_needs_a_destination_and_canvas_size():
    assert normalize_rect(None) is None
    assert normalize_rect({"canvasW": 256, "canvasH": 256}) is None
    assert normalize_rect({"dx": 1, "dy": 1}) is None
    assert normalize_rect({"dx": 1, "dy": 1, "canvasW": 0, "canvasH": 256}) is None


def test_normalize_rect_survives_missing_size():
    normalized = normalize_rect({"dx": 10, "dy": 20, "canvasW": 100, "canvasH": 200})
    assert normalized == {"x": 0.1, "y": 0.1, "cx": 0.1, "cy": 0.1}


# --------------------------------------------------------------------------- #
# Grid distance
# --------------------------------------------------------------------------- #


def test_grid_delta_is_zero_for_identical_grids():
    grid = [[0.25, 0.25], [0.25, 0.25]]
    assert grid_delta(grid, grid) == 0.0


def test_grid_delta_grows_when_alpha_mass_moves():
    before = [[0.5, 0.0], [0.0, 0.5]]
    after = [[0.0, 0.5], [0.5, 0.0]]
    assert grid_delta(before, after) == pytest.approx(1.0)


def test_grid_delta_is_zero_for_malformed_input():
    assert grid_delta(None, [[0.5]]) == 0.0
    assert grid_delta([[0.5]], None) == 0.0
    assert grid_delta([[0.5]], [[0.5, "x"]]) == 0.0


# --------------------------------------------------------------------------- #
# Baseline comparison
# --------------------------------------------------------------------------- #


def test_compare_reports_ok_for_identical_layouts():
    report = {
        "samples": [
            _sample("style:default", [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])])
        ]
    }
    diff = compare_sprite_layouts(report, report)
    assert diff["drift"] is False
    assert diff["missing"] == []
    assert diff["moved"] == []


def test_compare_detects_a_missing_sprite():
    baseline = {
        "samples": [
            _sample(
                "style:a",
                [
                    _asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)]),
                    _asset("img/face/tears-1.png", [_rect(96, 96, 16, 16)]),
                ],
            )
        ]
    }
    current = {
        "samples": [
            _sample("style:a", [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])])
        ]
    }
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is True
    assert diff["missing"] == [
        {"sample": "style:a", "src": "img/face/tears-1.png", "reason": "sprite_missing"}
    ]


def test_compare_detects_a_moved_sprite_beyond_tolerance():
    baseline = {
        "samples": [_sample("style:a", [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])])]
    }
    current = {
        "samples": [_sample("style:a", [_asset("img/face/blush-1.png", [_rect(96, 64, 32, 32)])])]
    }
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is True
    assert len(diff["moved"]) == 1
    assert diff["moved"][0]["delta"] == pytest.approx(0.125)


def test_compare_tolerates_jitter_within_the_position_tolerance():
    baseline = {
        "samples": [_sample("style:a", [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])])]
    }
    current = {
        "samples": [_sample("style:a", [_asset("img/face/blush-1.png", [_rect(65, 64, 32, 32)])])]
    }
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is False
    assert diff["moved"] == []


def test_compare_treats_new_sprites_as_information_not_drift():
    baseline = {
        "samples": [_sample("style:a", [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])])]
    }
    current = {
        "samples": [
            _sample(
                "style:a",
                [
                    _asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)]),
                    _asset("img/face/freckles-1.png", [_rect(10, 10, 8, 8)]),
                ],
            )
        ]
    }
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is False
    assert diff["new"] == [{"sample": "style:a", "src": "img/face/freckles-1.png"}]


def test_compare_detects_grid_drift():
    baseline = {
        "samples": [
            _sample(
                "style:a",
                [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])],
                grid=[[0.5, 0.0], [0.0, 0.5]],
            )
        ]
    }
    current = {
        "samples": [
            _sample(
                "style:a",
                [_asset("img/face/blush-1.png", [_rect(64, 64, 32, 32)])],
                grid=[[0.0, 0.5], [0.5, 0.0]],
            )
        ]
    }
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is True
    assert diff["grid_drift"] == [{"sample": "style:a", "delta": 1.0}]


def test_compare_reports_a_missing_sample():
    baseline = {
        "samples": [_sample("style:a", [_asset("img/face/blush-1.png", [_rect(1, 1, 2, 2)])])]
    }
    diff = compare_sprite_layouts(baseline, {"samples": []})
    assert diff["drift"] is True
    assert diff["missing"] == [{"sample": "style:a", "src": None, "reason": "sample_missing"}]


def test_compare_uses_the_last_recorded_rect_per_asset():
    baseline = {
        "samples": [
            _sample(
                "style:a",
                [
                    _asset(
                        "img/face/blush-1.png",
                        [_rect(0, 0, 8, 8), _rect(64, 64, 32, 32)],
                    )
                ],
            )
        ]
    }
    current = dict(baseline)
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is False


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("img/misc/sky/clouds/fog/2.png", True),
        ("img/misc/weather/rain/1.png", True),
        ("img/face/default/default/blush-1.png", False),
        ("img/misc/locations/home/base.png", False),
    ],
)
def test_is_animated_layer_matches_known_moving_backgrounds(src, expected):
    assert is_animated_layer(src) is expected


def test_compare_ignores_animated_layers_by_default():
    baseline = {
        "samples": [_sample("style:a", [_asset("img/misc/sky/clouds/fog/2.png", [_rect(4, 4, 8, 8)])])]
    }
    current = {
        "samples": [_sample("style:a", [_asset("img/misc/sky/clouds/fog/2.png", [_rect(40, 4, 8, 8)])])]
    }
    diff = compare_sprite_layouts(baseline, current)
    assert diff["drift"] is False
    assert diff["moved"] == []
    assert len(diff["ignored_moved"]) == 1
    assert diff["ignored_moved"][0]["src"] == "img/misc/sky/clouds/fog/2.png"


def test_compare_strict_mode_keeps_animated_layers_as_drift():
    baseline = {
        "samples": [_sample("style:a", [_asset("img/misc/sky/clouds/fog/2.png", [_rect(4, 4, 8, 8)])])]
    }
    current = {
        "samples": [_sample("style:a", [_asset("img/misc/sky/clouds/fog/2.png", [_rect(40, 4, 8, 8)])])]
    }
    diff = compare_sprite_layouts(baseline, current, ignore_animated_layers=False)
    assert diff["drift"] is True
    assert len(diff["moved"]) == 1
    assert diff["ignored_moved"] == []


# --------------------------------------------------------------------------- #
# Summary / highlights / baseline payload
# --------------------------------------------------------------------------- #


def test_build_summary_counts_samples_and_unique_sprites():
    samples = [
        _sample(
            "style:a",
            [
                _asset("img/face/blush-1.png", [_rect(1, 1, 2, 2)], count=2),
                _asset("img/body/body.png", [_rect(1, 1, 2, 2)]),
            ],
        ),
        _sample("style:b", [_asset("img/face/blush-1.png", [_rect(1, 1, 2, 2)])]),
    ]
    summary = build_summary(samples)
    assert summary["samples"] == 2
    assert summary["unique_sprites"] == 2
    assert summary["sprite_draw_records"] == 3
    assert summary["pet_canvas_samples_with_pixels"] == 2


def test_highlight_assets_keeps_face_and_body_layers_only():
    sample = _sample(
        "style:a",
        [
            _asset("img/face/default/blush-1.png", [_rect(64, 64, 32, 32)]),
            _asset("img/ui/frame.png", [_rect(0, 0, 8, 8)]),
            _asset("img/body/body.png", [_rect(0, 0, 16, 16)]),
        ],
    )
    highlights = highlight_assets(sample)
    sources = [item["src"] for item in highlights]
    assert "img/face/default/blush-1.png" in sources
    assert "img/body/body.png" in sources
    assert "img/ui/frame.png" not in sources
    assert highlights[0]["norm"]["cx"] == pytest.approx(0.3125)


def test_baseline_payload_strips_volatile_fields():
    report = {
        "schema": "dolx.sprite-layout.v1",
        "target": "C:/secret/path/build.zip",
        "html_path": "C:/secret/path/build.html",
        "target_sha256": "abc",
        "artifact_variant": "au-f",
        "samples": [{"id": "default"}],
        "summary": {"samples": 1},
        "console_tail": ["pageerror:boom"],
        "network_failures": [{"url": "img/x.png"}],
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "verdict": "ok",
        "diff": {"drift": False},
    }
    payload = baseline_payload(report)
    assert set(payload) == {
        "schema",
        "target_sha256",
        "artifact_variant",
        "samples",
        "summary",
    }
    assert "target" not in payload
    assert "console_tail" not in payload
    assert payload["samples"] == [{"id": "default"}]


# --------------------------------------------------------------------------- #
# Network recording / report writing / CLI
# --------------------------------------------------------------------------- #


def test_record_network_relativizes_and_hints_asset_failures():
    sink = []
    _record_network(
        sink,
        url="http://127.0.0.1:5555/img/face/default/blush2.png?v=1",
        status=404,
        kind="http_error",
    )
    assert sink[0]["url"] == "img/face/default/blush2.png"
    assert sink[0]["asset"] is True
    assert sink[0]["hint"] == "legacy_blush_tear_naming"


def test_record_network_stops_at_the_cap():
    sink = []
    for index in range(MAX_NETWORK_RECORDS + 5):
        _record_network(sink, url=f"img/a/{index}.png", status=404, kind="http_error")
    assert len(sink) == MAX_NETWORK_RECORDS


def test_write_report_emits_json_and_markdown(tmp_path):
    report = {
        "target": "build.zip",
        "artifact_variant": "au-f",
        "target_sha256": "abc",
        "verdict": "ok",
        "summary": {"samples": 1, "unique_sprites": 2},
        "network_failure_summary": {"total": 0},
        "samples": [{"id": "default", "pet_canvas": {}, "sprites": []}],
    }
    json_path = write_report(report, tmp_path)
    assert json_path == tmp_path / "sprite-layout.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "ok"
    markdown = (tmp_path / "sprite-layout.md").read_text(encoding="utf-8")
    assert "sprite layout probe" in markdown
    assert "sample default" in markdown


def test_parse_args_defaults_are_observation_first():
    args = parse_args(["build.zip"])
    assert args.target.name == "build.zip"
    assert args.out is None
    assert args.baseline is None
    assert args.update_baseline is False
    assert args.strict_layout is False
    assert args.max_styles == 8
