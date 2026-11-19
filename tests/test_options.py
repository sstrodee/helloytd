import os

import pytest

from app.formats import VIDEO_FORMAT, video_format_sort
from app.options import (
    ERROR_MESSAGES,
    PLAYLIST_PREVIEW_LIMIT,
    DownloadRequest,
    build_ydl_options,
    classify_error,
    friendly_error,
    info_ydl_options,
    needs_cookies,
    run_with_cookie_retry,
    summarize_result,
)


def make(**overrides):
    fields = {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw", "out_dir": "C:/Videos"}
    fields.update(overrides)
    return DownloadRequest(**fields)


def postprocessor(opts, key):
    found = [pp for pp in opts.get("postprocessors", []) if pp["key"] == key]
    return found[0] if found else None


def postprocessor_order(opts):
    return [pp["key"] for pp in opts.get("postprocessors", [])]


class TestVideo:
    def test_caps_quality_through_resolution_sort_and_merges_to_mp4(self):
        opts = build_ydl_options(make(mode="video", max_height=1080))
        assert opts["format"] == VIDEO_FORMAT
        assert opts["format_sort"] == video_format_sort(1080)
        assert opts["merge_output_format"] == "mp4"

    def test_best_quality_has_no_cap(self):
        assert build_ydl_options(make(mode="video"))["format_sort"] == video_format_sort(None)

    def test_does_not_extract_audio(self):
        opts = build_ydl_options(make(mode="video"))
        assert postprocessor(opts, "FFmpegExtractAudio") is None


class TestAudio:
    def test_mp3_reencodes_at_chosen_bitrate(self):
        opts = build_ydl_options(make(mode="audio", audio_codec="mp3", audio_bitrate=192))
        assert opts["format"] == "bestaudio/best"
        extract = postprocessor(opts, "FFmpegExtractAudio")
        assert extract["preferredcodec"] == "mp3"
        assert extract["preferredquality"] == "192"

    def test_m4a_prefers_native_m4a_stream(self):
        opts = build_ydl_options(make(mode="audio", audio_codec="m4a", audio_bitrate=None))
        assert opts["format"] == "bestaudio[ext=m4a]/bestaudio/best"
        assert postprocessor(opts, "FFmpegExtractAudio")["preferredcodec"] == "m4a"

    @pytest.mark.parametrize("codec", ["mp3", "m4a"])
    def test_embeds_jpg_cover_after_extraction(self, codec):
        opts = build_ydl_options(make(mode="audio", audio_codec=codec))
        assert opts["writethumbnail"] is True
        assert postprocessor(opts, "FFmpegThumbnailsConvertor")["format"] == "jpg"
        order = postprocessor_order(opts)
        assert order.index("FFmpegExtractAudio") < order.index("EmbedThumbnail")

    def test_audio_is_not_merged_as_video(self):
        assert "merge_output_format" not in build_ydl_options(make(mode="audio"))

    def test_prefers_stereo_soundtrack(self):
        assert build_ydl_options(make(mode="audio"))["format_sort"] == ["channels:2"]


class TestMetadata:
    @pytest.mark.parametrize("mode", ["video", "audio"])
    def test_title_and_chapters_are_written_into_file(self, mode):
        meta = postprocessor(build_ydl_options(make(mode=mode)), "FFmpegMetadata")
        assert meta["add_metadata"] is True
        assert meta["add_chapters"] is True


class TestOutput:
    def test_saves_into_chosen_folder_via_paths(self):
        opts = build_ydl_options(make(out_dir="D:/100% музыка"))
        assert opts["paths"]["home"] == "D:/100% музыка"
        assert "музыка" not in opts["outtmpl"]["default"]

    def test_single_video_is_named_by_title(self):
        assert build_ydl_options(make())["outtmpl"]["default"] == "%(title).140B [%(id)s].%(ext)s"


class TestPlaylist:
    def test_single_video_ignores_surrounding_playlist(self):
        assert build_ydl_options(make(is_playlist=False))["noplaylist"] is True

    def test_playlist_gets_own_numbered_folder(self):
        opts = build_ydl_options(make(is_playlist=True))
        assert opts["noplaylist"] is False
        assert opts["outtmpl"]["default"] == (
            "%(playlist_title).70B [%(playlist_id)s]/%(playlist_index)03d - %(title).140B [%(id)s].%(ext)s"
        )

    def test_selected_entries_become_sorted_items_spec(self):
        opts = build_ydl_options(make(is_playlist=True, playlist_items=(5, 1, 3)))
        assert opts["playlist_items"] == "1,3,5"

    def test_whole_playlist_when_nothing_selected(self):
        assert "playlist_items" not in build_ydl_options(make(is_playlist=True))

    def test_one_broken_entry_does_not_stop_the_rest(self):
        assert build_ydl_options(make(is_playlist=True))["ignoreerrors"] is True
        assert build_ydl_options(make(is_playlist=False)).get("ignoreerrors") is not True


class TestSubtitles:
    def test_off_by_default(self):
        assert not build_ydl_options(make()).get("writesubtitles")

    def test_fetches_manual_and_auto_ru_en_as_srt(self):
        opts = build_ydl_options(make(subtitles=True))
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is True
        assert opts["subtitleslangs"] == ["ru", "en"]
        assert postprocessor(opts, "FFmpegSubtitlesConvertor")["format"] == "srt"

    def test_ignored_for_audio(self):
        opts = build_ydl_options(make(mode="audio", subtitles=True))
        assert not opts.get("writesubtitles")


class TestTrim:
    def test_whole_video_by_default(self):
        assert build_ydl_options(make()).get("overwrites") is not True

    def test_fragment_downloads_only_the_selected_range_through_ffmpeg(self):
        opts = build_ydl_options(make(trim=(90.0, 240.0)))
        ranges = list(opts["download_ranges"]({"duration": 600}, None))
        assert ranges == [{"start_time": 90.0, "end_time": 240.0}]
        assert opts["force_keyframes_at_cuts"] is True
        assert "protocol=m3u8_native" in opts["format"]
        assert "height<=1080" in opts["format"]
        assert opts["external_downloader_args"]["ffmpeg_i"] == ["-rw_timeout", "15000000"]

    def test_fragment_respects_a_lower_quality_choice(self):
        opts = build_ydl_options(make(max_height=720, trim=(90.0, 240.0)))
        assert "height<=720" in opts["format"]

    def test_fragment_caps_higher_quality_at_segmented_1080p(self):
        opts = build_ydl_options(make(max_height=2160, trim=(90.0, 240.0)))
        assert "height<=1080" in opts["format"]

    def test_open_end_downloads_from_start_to_end_of_video(self):
        opts = build_ydl_options(make(trim=(90.0, None)))
        ranges = list(opts["download_ranges"]({"duration": 600}, None))
        assert ranges == [{"start_time": 90.0, "end_time": float("inf")}]

    def test_audio_range_keeps_stream_copy_until_final_conversion(self):
        opts = build_ydl_options(make(mode="audio", trim=(90.0, 240.0)))
        assert opts["force_keyframes_at_cuts"] is False
        assert opts["format"].startswith("bestaudio[protocol=m3u8_native]/")

    def test_fragment_preserves_existing_file(self):
        assert build_ydl_options(make(trim=(90.0, 240.0)))["overwrites"] is False

    def test_fragment_drops_chapters_that_no_longer_match(self):
        meta = postprocessor(build_ydl_options(make(trim=(90.0, 240.0))), "FFmpegMetadata")
        assert meta["add_chapters"] is False

    def test_fragment_gets_distinct_file_name(self):
        opts = build_ydl_options(make(trim=(90.0, 240.0)))
        assert opts["outtmpl"]["default"] == "%(title).125B [%(id)s] [1.30-4.00].%(ext)s"

    def test_ignored_for_playlists(self):
        opts = build_ydl_options(make(is_playlist=True, trim=(90.0, 240.0)))
        assert "[1.30-4.00]" not in opts["outtmpl"]["default"]
        assert opts.get("overwrites") is not True


class TestEnvironment:
    def test_routes_through_detected_proxy(self):
        opts = build_ydl_options(make(), proxy="http://127.0.0.1:10809")
        assert opts["proxy"] == "http://127.0.0.1:10809"

    def test_direct_route_disables_environment_proxy(self):
        assert build_ydl_options(make(), proxy=None)["proxy"] == ""

    def test_enables_found_js_runtime(self):
        opts = build_ydl_options(make(), js_runtime=("node", "C:/nodejs/node.exe"))
        assert opts["js_runtimes"] == {"node": {"path": "C:/nodejs/node.exe"}}

    def test_leaves_runtime_default_when_none_found(self):
        assert "js_runtimes" not in build_ydl_options(make(), js_runtime=None)

    def test_points_at_found_ffmpeg(self):
        opts = build_ydl_options(make(), ffmpeg_dir="C:/ffmpeg/bin")
        assert opts["ffmpeg_location"] == "C:/ffmpeg/bin"

    def test_reads_cookies_only_when_asked(self):
        assert "cookiesfrombrowser" not in build_ydl_options(make())
        opts = build_ydl_options(make(), cookies_browser="firefox")
        assert opts["cookiesfrombrowser"] == ("firefox",)

    def test_stays_quiet_for_gui(self):
        opts = build_ydl_options(make())
        assert opts["quiet"] is True
        assert opts["noprogress"] is True


class TestClassifyError:
    @pytest.mark.parametrize(
        "message,kind",
        [
            ("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol", "network"),
            ("Unable to download webpage: <urlopen error [WinError 10054] reset>", "network"),
            ("Unable to download API page: The read operation timed out", "network"),
            ("ProxyError: Unable to connect to proxy", "network"),
            ("Sign in to confirm you\u2019re not a bot. Use --cookies-from-browser", "bot_check"),
            ("Sign in to confirm your age. This video may be inappropriate", "age"),
            ("Private video. Sign in if you've been granted access to this video", "private"),
            ("Join this channel to get access to members-only content", "private"),
            ("Video unavailable. This video has been removed by the uploader", "unavailable"),
            ("Postprocessing: ffprobe and ffmpeg not found. Please install", "ffmpeg"),
            ("Unsupported URL: https://example.com/", "bad_url"),
            ("'not a link' is not a valid URL.", "bad_url"),
            ("Requested format is not available. Use --list-formats", "format"),
            ("unable to download video data: HTTP Error 403: Forbidden", "forbidden"),
            ("HTTP Error 429: Too Many Requests", "rate_limit"),
            ("[Errno 28] No space left on device", "disk_full"),
            ("[Errno 13] Permission denied: 'C:/Windows/x.mp4'", "no_access"),
            ("something nobody has seen before", "unknown"),
        ],
    )
    def test_maps_yt_dlp_messages_to_kinds(self, message, kind):
        assert classify_error(message) == kind

    def test_every_kind_has_a_message(self):
        kinds = {
            "network", "bot_check", "age", "private", "unavailable", "ffmpeg",
            "bad_url", "format", "forbidden", "rate_limit", "disk_full",
            "no_access", "unknown",
        }
        assert kinds <= set(ERROR_MESSAGES)


class TestNeedsCookies:
    @pytest.mark.parametrize(
        "message",
        [
            "Sign in to confirm you\u2019re not a bot.",
            "Sign in to confirm your age.",
            "Private video. Sign in if you've been granted access to this video",
        ],
    )
    def test_auth_walls_are_worth_retrying_with_cookies(self, message):
        assert needs_cookies(message)

    def test_network_failure_is_not(self):
        assert not needs_cookies("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred")


class TestFriendlyError:
    def test_known_kind_uses_its_message(self):
        assert friendly_error("HTTP Error 429: Too Many Requests") == ERROR_MESSAGES["rate_limit"]

    def test_unknown_error_keeps_original_detail(self):
        text = friendly_error("ERROR: [youtube] abc: something odd happened")
        assert text.startswith(ERROR_MESSAGES["unknown"])
        assert "something odd happened" in text
        assert "ERROR:" not in text


class TestInfoOptions:
    def test_lists_playlist_entries_without_opening_each_video(self):
        opts = info_ydl_options(as_playlist=True)
        assert opts["extract_flat"] == "in_playlist"
        assert opts["noplaylist"] is False
        assert opts["skip_download"] is True

    def test_video_link_with_list_param_opens_only_the_video(self):
        assert info_ydl_options(as_playlist=False)["noplaylist"] is True

    def test_long_playlists_are_previewed_partially(self):
        assert info_ydl_options(as_playlist=True)["playlistend"] == PLAYLIST_PREVIEW_LIMIT

    def test_shares_network_settings_with_downloads(self):
        opts = info_ydl_options(
            as_playlist=False,
            proxy="http://127.0.0.1:10809",
            js_runtime=("node", "C:/node.exe"),
            cookies_browser="firefox",
        )
        assert opts["proxy"] == "http://127.0.0.1:10809"
        assert opts["js_runtimes"] == {"node": {"path": "C:/node.exe"}}
        assert opts["cookiesfrombrowser"] == ("firefox",)


class TestCookieRetry:
    @staticmethod
    def scripted(*outcomes):
        calls = []

        def attempt(browser):
            calls.append(browser)
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return attempt, calls

    def test_first_try_goes_without_cookies(self):
        attempt, calls = self.scripted("ok")
        assert run_with_cookie_retry(attempt, "firefox", "auto") == "ok"
        assert calls == [None]

    def test_login_wall_is_retried_with_browser_cookies(self):
        attempt, calls = self.scripted(RuntimeError("Sign in to confirm you are not a bot"), "ok")
        retried = []
        result = run_with_cookie_retry(attempt, "firefox", "auto", on_retry=lambda: retried.append(1))
        assert result == "ok"
        assert calls == [None, "firefox"]
        assert retried == [1]

    def test_other_errors_are_not_retried(self):
        attempt, calls = self.scripted(RuntimeError("HTTP Error 429: Too Many Requests"))
        with pytest.raises(RuntimeError):
            run_with_cookie_retry(attempt, "firefox", "auto")
        assert calls == [None]

    def test_always_mode_uses_cookies_from_the_start(self):
        attempt, calls = self.scripted("ok")
        run_with_cookie_retry(attempt, "firefox", "always")
        assert calls == ["firefox"]

    def test_never_mode_does_not_touch_the_browser(self):
        attempt, calls = self.scripted(RuntimeError("Sign in to confirm your age"))
        with pytest.raises(RuntimeError):
            run_with_cookie_retry(attempt, "firefox", "never")
        assert calls == [None]


class TestSummarizeResult:
    def test_single_video_reports_its_file(self):
        info = {"requested_downloads": [{"filepath": "C:/Videos/zoo.mp4"}]}
        assert summarize_result(info, is_playlist=False) == (True, "", "C:/Videos/zoo.mp4")

    def test_single_video_without_file_is_a_failure(self):
        ok, message, path = summarize_result({}, is_playlist=False)
        assert ok is False
        assert message
        assert path == ""

    def test_nothing_returned_is_a_failure(self):
        ok, _, path = summarize_result(None, is_playlist=True)
        assert ok is False
        assert path == ""

    def test_playlist_reports_its_folder(self):
        first = "C:/Videos/List/001 - a.mp4"
        info = {"entries": [
            {"requested_downloads": [{"filepath": first}]},
            {"requested_downloads": [{"filepath": "C:/Videos/List/002 - b.mp4"}]},
        ]}
        assert summarize_result(info, is_playlist=True) == (True, "", os.path.dirname(first))

    def test_partly_failed_playlist_says_how_many_made_it(self):
        info = {"entries": [{"requested_downloads": [{"filepath": "C:/V/L/1.mp4"}]}, None, None]}
        ok, message, path = summarize_result(info, is_playlist=True)
        assert ok is True
        assert "1 из 3" in message
        assert path == os.path.dirname("C:/V/L/1.mp4")

    def test_playlist_where_nothing_downloaded_is_a_failure(self):
        ok, message, path = summarize_result({"entries": [None, None]}, is_playlist=True)
        assert ok is False
        assert message
        assert path == ""
