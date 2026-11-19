import os

from app.environment import find_ffmpeg_dir, find_js_runtime


def which_from(found):
    return lambda name: found.get(name)


def no_matches(*args, **kwargs):
    return []


class TestFindJsRuntime:
    def test_prefers_deno_when_several_are_installed(self):
        which = which_from({"node": "C:/nodejs/node.exe", "deno": "C:/deno/deno.exe"})
        assert find_js_runtime(which=which, isfile=lambda path: False) == ("deno", "C:/deno/deno.exe")

    def test_uses_node_from_path(self):
        which = which_from({"node": "C:/nodejs/node.exe"})
        assert find_js_runtime(which=which, isfile=lambda path: False) == ("node", "C:/nodejs/node.exe")

    def test_falls_back_to_default_install_location(self):
        name, path = find_js_runtime(
            which=which_from({}), isfile=lambda path: path.lower().endswith("node.exe")
        )
        assert name == "node"
        assert path.lower().endswith("node.exe")

    def test_none_when_nothing_is_installed(self):
        assert find_js_runtime(which=which_from({}), isfile=lambda path: False) is None


class TestFindFfmpegDir:
    def test_uses_ffmpeg_on_path(self):
        which = which_from({"ffmpeg": "C:/tools/ffmpeg/bin/ffmpeg.exe"})
        assert find_ffmpeg_dir(which=which, glob=no_matches) == "C:/tools/ffmpeg/bin"

    def test_finds_winget_install_when_not_on_path(self):
        hit = "C:/W/Packages/Gyan.FFmpeg_x/ffmpeg-8.1-full_build/bin/ffmpeg.exe"
        found = find_ffmpeg_dir(which=which_from({}), glob=lambda *args, **kwargs: [hit])
        assert found == os.path.dirname(hit)

    def test_picks_newest_of_several_winget_builds(self):
        old = "C:/W/Packages/Gyan.FFmpeg_x/ffmpeg-7.1-full_build/bin/ffmpeg.exe"
        new = "C:/W/Packages/Gyan.FFmpeg_x/ffmpeg-8.1-full_build/bin/ffmpeg.exe"
        found = find_ffmpeg_dir(which=which_from({}), glob=lambda *args, **kwargs: [new, old])
        assert found == os.path.dirname(new)

    def test_none_when_missing(self):
        assert find_ffmpeg_dir(which=which_from({}), glob=no_matches) is None
