import pytest

from app.links import has_playlist_param, is_youtube_url, normalize_url


class TestIsYoutubeUrl:
    @pytest.mark.parametrize(
        "text",
        [
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            "https://youtu.be/jNQXAC9IVRw",
            "https://m.youtube.com/watch?v=jNQXAC9IVRw",
            "https://music.youtube.com/watch?v=jNQXAC9IVRw",
            "https://www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com/playlist?list=PL123",
            "  https://youtu.be/jNQXAC9IVRw  ",
        ],
    )
    def test_recognises_youtube_links(self, text):
        assert is_youtube_url(text)

    @pytest.mark.parametrize(
        "text",
        [
            "https://example.com/watch?v=jNQXAC9IVRw",
            "https://notyoutube.com/watch?v=x",
            "https://youtube.com.evil.example/watch?v=x",
            "просто текст",
            "https://youtu.be/a\nhttps://youtu.be/b",
            "",
            None,
        ],
    )
    def test_ignores_everything_else(self, text):
        assert not is_youtube_url(text)


class TestNormalizeUrl:
    def test_trims_whitespace(self):
        assert normalize_url("  https://youtu.be/x \n") == "https://youtu.be/x"

    def test_adds_missing_scheme(self):
        assert normalize_url("youtu.be/x") == "https://youtu.be/x"
        assert normalize_url("www.youtube.com/watch?v=x") == "https://www.youtube.com/watch?v=x"

    def test_keeps_existing_scheme(self):
        assert normalize_url("http://example.com/v") == "http://example.com/v"

    def test_leaves_plain_text_alone(self):
        assert normalize_url("просто текст") == "просто текст"


class TestHasPlaylistParam:
    def test_video_opened_from_playlist(self):
        assert has_playlist_param("https://www.youtube.com/watch?v=x&list=PL123&index=3")

    def test_plain_video(self):
        assert not has_playlist_param("https://www.youtube.com/watch?v=x")

    def test_playlist_page_itself(self):
        assert has_playlist_param("https://www.youtube.com/playlist?list=PL123")
