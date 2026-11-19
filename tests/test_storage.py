import json

from app.storage import (
    DEFAULT_SETTINGS,
    app_data_dir,
    append_history,
    clear_history,
    load_history,
    keep_caches_inside,
    load_settings,
    save_settings,
)


class TestAppDataDir:
    def test_lives_next_to_the_program(self, tmp_path):
        # Portable: всё своё — в папке программы; удалил папку — следов нет.
        assert app_data_dir(tmp_path) == tmp_path / "data"
        assert (tmp_path / "data").is_dir()

    def test_falls_back_to_appdata_when_the_program_folder_is_not_writable(self, tmp_path):
        (tmp_path / "data").write_text("на месте папки — файл, создать её нельзя", encoding="utf-8")
        roaming = tmp_path / "roaming"
        assert app_data_dir(tmp_path, appdata=str(roaming)) == roaming / "helloytd"


class TestKeepCachesInside:
    def test_yt_dlp_and_deno_caches_go_into_the_data_folder(self, tmp_path):
        # Иначе yt-dlp пишет в ~\.cache\yt-dlp, а Deno — в %LOCALAPPDATA%\deno.
        environ = {}
        keep_caches_inside(tmp_path, environ)
        assert environ["XDG_CACHE_HOME"] == str(tmp_path / "cache")
        assert environ["DENO_DIR"] == str(tmp_path / "cache" / "deno")


class TestSettings:
    def test_missing_file_gives_defaults(self, tmp_path):
        assert load_settings(tmp_path / "settings.json") == DEFAULT_SETTINGS

    def test_round_trip_keeps_changes(self, tmp_path):
        path = tmp_path / "settings.json"
        settings = dict(DEFAULT_SETTINGS, out_dir="D:/Видео", mode="audio")
        save_settings(path, settings)
        assert load_settings(path) == settings

    def test_creates_missing_folder(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "settings.json"
        save_settings(path, DEFAULT_SETTINGS)
        assert path.exists()

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_settings(path) == DEFAULT_SETTINGS

    def test_missing_keys_are_filled_and_unknown_dropped(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"mode": "audio", "legacy": 1}), encoding="utf-8")
        loaded = load_settings(path)
        assert loaded["mode"] == "audio"
        assert loaded["cookies_browser"] == DEFAULT_SETTINGS["cookies_browser"]
        assert "legacy" not in loaded

    def test_callers_cannot_mutate_defaults(self, tmp_path):
        loaded = load_settings(tmp_path / "settings.json")
        loaded["mode"] = "audio"
        assert DEFAULT_SETTINGS["mode"] == "video"


class TestHistory:
    def test_empty_when_missing(self, tmp_path):
        assert load_history(tmp_path / "history.json") == []

    def test_newest_first(self, tmp_path):
        path = tmp_path / "history.json"
        append_history(path, {"title": "первое"})
        append_history(path, {"title": "второе"})
        assert [entry["title"] for entry in load_history(path)] == ["второе", "первое"]

    def test_keeps_only_recent_entries(self, tmp_path):
        path = tmp_path / "history.json"
        for number in range(5):
            append_history(path, {"title": str(number)}, limit=3)
        assert [entry["title"] for entry in load_history(path)] == ["4", "3", "2"]

    def test_corrupt_history_is_treated_as_empty(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text("[[[", encoding="utf-8")
        assert load_history(path) == []

    def test_clear_forgets_everything(self, tmp_path):
        path = tmp_path / "history.json"
        append_history(path, {"title": "x"})
        clear_history(path)
        assert load_history(path) == []
