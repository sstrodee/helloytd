from app.preview import summarize

ZOO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL1"


def video_info(**overrides):
    info = {
        "id": "jNQXAC9IVRw",
        "title": "Me at the zoo",
        "uploader": "jawed",
        "duration": 19,
        "formats": [
            {"vcodec": "avc1", "width": 1920, "height": 1080},
            {"vcodec": "none", "acodec": "mp4a"},
        ],
        "thumbnails": [
            {"url": "https://i.ytimg.com/a.jpg", "width": 120, "height": 90},
            {"url": "https://i.ytimg.com/b.jpg", "width": 336, "height": 188},
            {"url": "https://i.ytimg.com/c.jpg", "width": 1280, "height": 720},
        ],
        "subtitles": {},
        "automatic_captions": {"en": [{}]},
    }
    info.update(overrides)
    return info


def playlist_info(**overrides):
    info = {
        "_type": "playlist",
        "title": "Blender shorts",
        "uploader": "Blender",
        "entries": [
            {"id": "a", "title": "Первое", "duration": 60},
            None,
            {"id": "c", "title": "Третье", "duration": None},
        ],
        "thumbnails": [{"url": "https://i.ytimg.com/pl.jpg", "width": 480, "height": 270}],
    }
    info.update(overrides)
    return info


class TestVideoPreview:
    def test_basic_fields(self):
        preview = summarize(video_info(), ZOO_URL)
        assert preview.kind == "video"
        assert preview.url == ZOO_URL
        assert preview.title == "Me at the zoo"
        assert preview.uploader == "jawed"
        assert preview.duration == 19

    def test_offers_qualities_the_video_actually_has(self):
        assert summarize(video_info(), ZOO_URL).tiers == (1080, 720, 480, 360)

    def test_picks_smallest_thumbnail_that_still_looks_sharp(self):
        assert summarize(video_info(), ZOO_URL).thumbnail_url == "https://i.ytimg.com/b.jpg"

    def test_falls_back_to_single_thumbnail_field(self):
        info = video_info(thumbnails=None, thumbnail="https://i.ytimg.com/x.jpg")
        assert summarize(info, ZOO_URL).thumbnail_url == "https://i.ytimg.com/x.jpg"

    def test_auto_captions_count_as_subtitles(self):
        assert summarize(video_info(), ZOO_URL).has_subtitles is True
        assert summarize(video_info(automatic_captions={}), ZOO_URL).has_subtitles is False

    def test_uses_channel_when_uploader_is_missing(self):
        info = video_info(uploader=None, channel="Blender")
        assert summarize(info, ZOO_URL).uploader == "Blender"

    def test_untitled_video_gets_placeholder(self):
        assert summarize(video_info(title=None), ZOO_URL).title == "Без названия"

    def test_notices_playlist_in_link(self):
        assert summarize(video_info(), ZOO_URL + "&list=PL1").in_playlist is True
        assert summarize(video_info(), ZOO_URL).in_playlist is False


class TestPlaylistPreview:
    def test_lists_entries_with_their_playlist_numbers(self):
        preview = summarize(playlist_info(), PLAYLIST_URL)
        assert preview.kind == "playlist"
        assert preview.entries == ((1, "Первое", 60), (3, "Третье", None))

    def test_quality_is_unknown_until_each_video_is_opened(self):
        assert summarize(playlist_info(), PLAYLIST_URL).tiers == ()

    def test_uses_playlist_cover(self):
        assert summarize(playlist_info(), PLAYLIST_URL).thumbnail_url == "https://i.ytimg.com/pl.jpg"

    def test_borrows_cover_from_first_video_when_playlist_has_none(self):
        info = playlist_info(thumbnails=None)
        info["entries"][0]["thumbnails"] = [{"url": "https://i.ytimg.com/first.jpg", "width": 336}]
        assert summarize(info, PLAYLIST_URL).thumbnail_url == "https://i.ytimg.com/first.jpg"
