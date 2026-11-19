import pytest

from app.progress import DOWNLOADING, STAGE_LABELS, Progress, ProgressTracker, describe_detail


def hook(status="downloading", fmt="137", done=0, total=None, estimate=None, speed=None,
         eta=None, video_id="v1", item=None, count=None, elapsed=5.0, fragment=None):
    # Как у настоящего yt-dlp: в событии потока нет requested_formats — он их удаляет.
    info = {"id": video_id, "format_id": fmt}
    if item is not None:
        info["playlist_autonumber"] = item
        info["n_entries"] = count
    event = {
        "status": status, "downloaded_bytes": done, "total_bytes": total,
        "total_bytes_estimate": estimate, "speed": speed, "eta": eta, "elapsed": elapsed,
        "info_dict": info,
    }
    if fragment is not None:
        event["fragment_index"], event["fragment_count"] = fragment
    return event


def plan(tracker, streams, video_id="v1"):
    """Как шаг before_dl: из каких потоков соберётся видео, известно до загрузки."""
    tracker.plan({
        "id": video_id,
        "requested_formats": [
            {"format_id": fid, "filesize": size, "vcodec": vcodec} for fid, size, vcodec in streams
        ],
    })


class TestSingleStream:
    def test_fraction_speed_and_eta_come_from_the_hook(self):
        progress = ProgressTracker().on_download(hook(done=250, total=1000, speed=2048, eta=7))
        assert progress.fraction == pytest.approx(0.25)
        assert progress.speed == 2048
        assert progress.eta == 7

    def test_estimate_is_used_when_exact_size_is_unknown(self):
        progress = ProgressTracker().on_download(hook(done=50, estimate=200))
        assert progress.fraction == pytest.approx(0.25)

    def test_unknown_size_gives_indeterminate_progress(self):
        assert ProgressTracker().on_download(hook(done=50)).fraction is None

    def test_finished_stream_is_complete(self):
        assert ProgressTracker().on_download(hook(status="finished", done=10)).fraction == 1.0

    def test_speed_is_hidden_until_it_settles(self):
        # Первое событие приходит раньше данных: «455 Б/с» на старте только пугает.
        progress = ProgressTracker().on_download(hook(done=712, estimate=10**6, speed=455, eta=9, elapsed=0.2))
        assert progress.speed is None
        assert progress.eta is None


class TestSideFiles:
    def test_subtitle_file_does_not_count_as_the_video(self):
        # Субтитры качаются тем же загрузчиком до видео, и в их событии нет format_id:
        # без этой проверки полоса показала бы 100%, а потом 0% на самом видео.
        subtitles = {"status": "finished", "downloaded_bytes": 416, "total_bytes": 416,
                     "info_dict": {"ext": "vtt", "url": "https://example.com/sub.vtt"}}
        assert ProgressTracker().on_download(subtitles).fraction is None


class TestFragmentedStream:
    def test_counts_fragments_not_the_jumpy_size_estimate(self):
        # HLS: в начале оценка размера равна скачанному — было бы 100% на первом же событии.
        first = ProgressTracker().on_download(hook(done=712, estimate=712, fragment=(0, 123)))
        assert first.fraction == 0.0
        later = ProgressTracker().on_download(hook(done=10**8, estimate=13 * 10**8, fragment=(31, 123)))
        assert later.fraction == pytest.approx(31 / 123)


class TestMergedStreams:
    def test_bar_is_weighted_by_expected_stream_sizes(self):
        tracker = ProgressTracker()
        plan(tracker, [("137", 900, "avc1"), ("140", 100, "none")])
        video_half = tracker.on_download(hook(fmt="137", done=450, total=900))
        assert video_half.fraction == pytest.approx(0.45)
        video_done = tracker.on_download(hook(status="finished", fmt="137", done=900, total=900))
        assert video_done.fraction == pytest.approx(0.9)
        audio_half = tracker.on_download(hook(fmt="140", done=50, total=100))
        assert audio_half.fraction == pytest.approx(0.95)

    def test_sound_does_not_send_the_bar_back_to_zero(self):
        # Так и было вживую: 0% → 50% на картинке, потом снова 0% на звуке.
        tracker = ProgressTracker()
        plan(tracker, [("137", 900, "avc1"), ("140", 100, "none")])
        tracker.on_download(hook(status="finished", fmt="137", done=900, total=900))
        assert tracker.on_download(hook(fmt="140", done=0, total=100)).fraction == pytest.approx(0.9)

    def test_video_outweighs_audio_when_sizes_are_unknown(self):
        # У 4K по HLS размер заранее неизвестен; поровну — полоса ползла бы до 50%
        # две минуты, а потом прыгала до 100% за секунду звука.
        tracker = ProgressTracker()
        plan(tracker, [("628", None, "vp09"), ("140", 10**7, "none")])
        video_half = tracker.on_download(hook(fmt="628", done=1, total=2))
        assert video_half.fraction == pytest.approx(0.45)
        tracker.on_download(hook(status="finished", fmt="628", done=2, total=2))
        audio_half = tracker.on_download(hook(fmt="140", done=1, total=2))
        assert audio_half.fraction == pytest.approx(0.95)

    def test_without_a_plan_each_stream_counts_on_its_own(self):
        assert ProgressTracker().on_download(hook(fmt="140", done=50, total=100)).fraction == pytest.approx(0.5)


class TestPlaylist:
    def test_bar_covers_the_whole_playlist(self):
        progress = ProgressTracker().on_download(hook(done=50, total=100, item=2, count=4))
        assert progress.fraction == pytest.approx(0.375)
        assert (progress.item, progress.item_count) == (2, 4)

    def test_next_video_starts_its_streams_from_scratch(self):
        tracker = ProgressTracker()
        both = [("137", 900, "avc1"), ("140", 100, "none")]
        plan(tracker, both, video_id="a")
        for fmt, size, _codec in both:
            tracker.on_download(hook(status="finished", fmt=fmt, done=size, total=size,
                                     video_id="a", item=1, count=2))
        plan(tracker, both, video_id="b")
        progress = tracker.on_download(hook(fmt="137", done=0, total=900, video_id="b", item=2, count=2))
        assert progress.fraction == pytest.approx(0.5)


class TestPostprocessing:
    def test_known_step_changes_the_caption_and_keeps_the_bar(self):
        tracker = ProgressTracker()
        tracker.on_download(hook(status="finished", done=10))
        progress = tracker.on_postprocess({"status": "started", "postprocessor": "Merger"})
        assert progress.stage == STAGE_LABELS["Merger"]
        assert progress.fraction == 1.0
        assert progress.speed is None

    def test_internal_steps_are_ignored(self):
        step = {"status": "started", "postprocessor": "MoveFiles"}
        assert ProgressTracker().on_postprocess(step) is None

    def test_step_completion_is_ignored(self):
        step = {"status": "finished", "postprocessor": "Merger"}
        assert ProgressTracker().on_postprocess(step) is None


class TestStageLabels:
    @pytest.mark.parametrize(
        "step",
        ["FFmpegMergerPP", "FFmpegExtractAudioPP", "FFmpegMetadataPP", "EmbedThumbnailPP",
         "FFmpegSubtitlesConvertorPP", "FFmpegThumbnailsConvertorPP"],
    )
    def test_labels_use_the_names_yt_dlp_reports(self, step):
        import yt_dlp.postprocessor as postprocessors

        assert getattr(postprocessors, step).pp_key() in STAGE_LABELS

class TestDescribeDetail:
    # Процент окно показывает крупно отдельно, в подписи он лишний.
    def test_speed_and_time_left_without_the_percent(self):
        progress = Progress(0.64, 2.1 * 1024 * 1024, 12, DOWNLOADING)
        assert describe_detail(progress) == "2,1 МБ/с, осталось 12 с"

    def test_playlist_says_which_video(self):
        assert describe_detail(Progress(0.5, None, None, DOWNLOADING, 3, 12)) == "Видео 3 из 12"

    def test_playlist_with_speed_joins_with_commas(self):
        progress = Progress(0.5, 2.1 * 1024 * 1024, None, DOWNLOADING, 3, 12)
        assert describe_detail(progress) == "Видео 3 из 12, 2,1 МБ/с"

    def test_unknown_numbers_are_left_out(self):
        assert describe_detail(Progress(None, None, None, DOWNLOADING)) == "Скачивание…"

    def test_postprocessing_shows_the_step(self):
        merging = STAGE_LABELS["Merger"]
        assert describe_detail(Progress(1.0, None, None, merging)) == merging

    def test_before_first_event(self):
        assert describe_detail(None) == "Подготовка…"
