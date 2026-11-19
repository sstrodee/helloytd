import pytest

from app.formats import (
    VIDEO_FORMAT,
    format_bytes,
    format_duration,
    format_eta,
    format_speed,
    parse_range,
    parse_timecode,
    quality_tiers,
    tier_name,
    tier_of,
    trim_label,
    video_format_sort,
)


class TestVideoFormat:
    def test_prefers_mp4_pair_then_falls_back(self):
        assert VIDEO_FORMAT == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"


class TestVideoFormatSort:
    def test_best_quality_sorts_by_resolution_without_cap(self):
        assert video_format_sort(None)[0] == "res"

    def test_cap_goes_through_resolution_sort(self):
        # res — меньшая сторона кадра, поэтому потолок работает и для
        # вертикальных роликов, и для широкоформатного кино.
        assert video_format_sort(1080)[0] == "res:1080"

    def test_codec_preference_comes_after_resolution(self):
        sort = video_format_sort(720)
        assert sort.index("vcodec:h264") > sort.index("res:720")

    def test_prefers_stereo_soundtrack(self):
        # 5.1-дорожка у YouTube тяжелее картинки в 360p, а на обычных колонках звучит так же.
        assert "channels:2" in video_format_sort(None)

    def test_rejects_nonpositive_height(self):
        with pytest.raises(ValueError):
            video_format_sort(0)


class TestTierOf:
    @pytest.mark.parametrize(
        "width,height,tier",
        [
            (3840, 2160, 2160),
            (1920, 1080, 1080),
            (1280, 720, 720),
            (1920, 800, 1080),   # широкоформатное кино
            (1440, 1080, 1080),  # 4:3
            (1080, 1920, 1080),  # вертикальное
            (1280, 534, 720),
            (320, 240, 240),
            (256, 144, 144),
        ],
    )
    def test_matches_youtube_quality_names(self, width, height, tier):
        assert tier_of(width, height) == tier

    def test_unknown_size(self):
        assert tier_of(None, None) is None


class TestQualityTiers:
    def test_offers_tiers_up_to_the_best_available(self):
        formats = [
            {"vcodec": "avc1", "width": 1920, "height": 1080},
            {"vcodec": "avc1", "width": 640, "height": 360},
        ]
        assert quality_tiers(formats) == [1080, 720, 480, 360]

    def test_ignores_audio_only_and_storyboard_formats(self):
        formats = [
            {"vcodec": "none", "acodec": "opus"},
            {"vcodec": "none", "acodec": "none", "width": 3840, "height": 2160},
            {"vcodec": "vp9", "width": 1280, "height": 720},
        ]
        assert quality_tiers(formats) == [720, 480, 360]

    def test_tiny_videos_offer_no_choice(self):
        assert quality_tiers([{"vcodec": "avc1", "width": 320, "height": 240}]) == []

    def test_no_video_means_no_tiers(self):
        assert quality_tiers([{"vcodec": "none"}]) == []


class TestTierName:
    @pytest.mark.parametrize(
        "tier,name",
        [(2160, "2160p, 4K"), (1080, "1080p, Full HD"), (720, "720p, HD"), (480, "480p")],
    )
    def test_names_tiers_like_youtube(self, tier, name):
        assert tier_name(tier) == name


class TestParseTimecode:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("90", 90.0),
            ("1:30", 90.0),
            ("01:30", 90.0),
            ("1:02:03", 3723.0),
            ("00:01:30.5", 90.5),
            ("  1:30  ", 90.0),
        ],
    )
    def test_accepts_common_timecode_shapes(self, text, expected):
        assert parse_timecode(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", "abc", "1:2:3:4", "-5", "1:60"])
    def test_rejects_malformed_timecode(self, text):
        with pytest.raises(ValueError):
            parse_timecode(text)


class TestParseRange:
    def test_returns_pair_of_seconds(self):
        assert parse_range("0:10", "1:40") == (10.0, 100.0)

    def test_empty_start_means_from_beginning(self):
        assert parse_range("", "1:40") == (0.0, 100.0)

    def test_empty_end_means_until_end_of_video(self):
        assert parse_range("1:40", "") == (100.0, None)

    def test_both_empty_means_no_trim(self):
        assert parse_range("", "") is None

    def test_enabled_fragment_requires_at_least_one_boundary(self):
        with pytest.raises(ValueError, match="начало или конец"):
            parse_range("", "", required=True)

    def test_rejects_end_before_start(self):
        with pytest.raises(ValueError):
            parse_range("2:00", "1:00")

    def test_rejects_equal_endpoints(self):
        with pytest.raises(ValueError):
            parse_range("1:00", "1:00")

    def test_rejects_start_beyond_video(self):
        with pytest.raises(ValueError, match="начало.*за пределами"):
            parse_range("2:00", "", duration=60)

    def test_rejects_end_beyond_video(self):
        with pytest.raises(ValueError, match="конец.*за пределами"):
            parse_range("0:10", "2:00", duration=60)


class TestTrimLabel:
    @pytest.mark.parametrize(
        "start,end,expected",
        [
            (90.0, 240.0, "1.30-4.00"),
            (0.0, 59.0, "0.00-0.59"),
            (5.9, 65.2, "0.05,9-1.05,2"),
            (3723.0, None, "1.02.03-конец"),
            (0.0, 3600.0, "0.00-1.00.00"),
        ],
    )
    def test_formats_fragment_for_file_name(self, start, end, expected):
        assert trim_label(start, end) == expected


class TestHumanReadable:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, "0 Б"),
            (512, "512 Б"),
            (1024, "1,0 КБ"),
            (1536, "1,5 КБ"),
            (1048576, "1,0 МБ"),
            (1073741824, "1,0 ГБ"),
        ],
    )
    def test_format_bytes(self, value, expected):
        assert format_bytes(value) == expected

    def test_format_bytes_handles_unknown(self):
        assert format_bytes(None) == "—"

    def test_format_speed_appends_per_second(self):
        assert format_speed(1048576) == "1,0 МБ/с"

    def test_format_speed_handles_unknown(self):
        assert format_speed(None) == "—"

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0 с"),
            (45, "45 с"),
            (90, "1 мин 30 с"),
            (3600, "1 ч 0 мин"),
            (3725, "1 ч 2 мин"),
        ],
    )
    def test_format_eta(self, seconds, expected):
        assert format_eta(seconds) == expected

    def test_format_eta_handles_unknown(self):
        assert format_eta(None) == "—"


class TestFormatDuration:
    @pytest.mark.parametrize(
        "seconds,expected",
        [(19, "0:19"), (635, "10:35"), (3723, "1:02:03"), (59.9, "0:59")],
    )
    def test_reads_like_youtube(self, seconds, expected):
        assert format_duration(seconds) == expected

    def test_unknown_duration_is_blank(self):
        assert format_duration(None) == ""
