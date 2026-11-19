from PySide6.QtWidgets import QApplication

from app import theme
from app.jobs import RUNNING, Job
from app.preview import Preview
from app.progress import DOWNLOADING, Progress
from app.widgets import ChoiceGrid, ClampedLabel, Field, JobRow
from app.window import MainWindow

app = QApplication.instance() or QApplication([])
theme.load_fonts()

LONG = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"


def make(text, lines=2):
    label = ClampedLabel(text, lines=lines)
    label.setFont(theme.sans_font(14))
    return label


def test_short_text_stays_on_one_line():
    assert make("Me at the zoo").visible_lines(400) == ["Me at the zoo"]


def test_long_text_wraps_up_to_the_limit_and_ends_with_ellipsis():
    lines = make(LONG * 3).visible_lines(200)
    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_text_that_fits_in_the_limit_is_not_cut():
    lines = make(LONG).visible_lines(260)
    assert len(lines) == 2
    assert not lines[-1].endswith("…")
    assert " ".join(lines) == LONG


def test_explicit_line_breaks_are_kept():
    assert make("первая\nвторая", lines=3).visible_lines(400) == ["первая", "вторая"]


def test_height_follows_the_number_of_lines():
    label = make(LONG)
    step = label.fontMetrics().lineSpacing()
    assert label.heightForWidth(1000) == step
    assert label.heightForWidth(260) == 2 * step


# ----- ChoiceGrid: пилюли качества ------------------------------------------

CHOICES = [(None, "лучшее", ""), (1080, "1080p", ""), (720, "720p", ""), (360, "360p", "")]


def test_choice_grid_selects_the_requested_value():
    grid = ChoiceGrid()
    grid.set_choices(CHOICES, 720, columns=4)
    assert grid.value() == 720


def test_choice_grid_falls_back_to_the_first_choice():
    grid = ChoiceGrid()
    grid.set_choices(CHOICES, 2160, columns=4)
    assert grid.value() is None


def test_choice_grid_click_changes_value_and_reports_it():
    grid = ChoiceGrid()
    grid.set_choices(CHOICES, None, columns=4)
    seen = []
    grid.changed.connect(seen.append)
    grid.buttons()[2].click()
    assert grid.value() == 720
    assert seen == [720]


def test_choice_grid_replaces_old_choices():
    grid = ChoiceGrid()
    grid.set_choices(CHOICES, None, columns=4)
    grid.set_choices([("mp3-320", "mp3 320", ""), ("m4a", "m4a", "")], "m4a", columns=3)
    assert [button.text() for button in grid.buttons()] == ["mp3 320", "m4a"]
    assert grid.value() == "m4a"


def test_choice_grid_set_value_does_not_report_a_change():
    grid = ChoiceGrid()
    grid.set_choices(CHOICES, None, columns=4)
    seen = []
    grid.changed.connect(seen.append)
    grid.set_value(1080)
    assert grid.value() == 1080
    assert seen == []


def test_choice_grid_keeps_every_row_inside_its_bounds():
    grid = ChoiceGrid()
    grid.set_choices(CHOICES, None, columns=2)
    grid.show()
    app.processEvents()
    assert grid.height() == 70
    assert all(grid.rect().contains(button.geometry()) for button in grid.buttons())
    grid.close()


# ----- Field: по имени поля стили красят всё на нём светлым -----------------

def test_field_is_named_for_the_light_text_styles():
    assert Field().objectName() == "field"


# ----- JobRow: прогресс не дублируется, пока загрузка крупно на поле ---------

def running_row():
    job = Job(title="Big Buck Bunny", request=None, state=RUNNING,
              progress=Progress(0.39, 11 * 1024 * 1024, 3, DOWNLOADING))
    row = JobRow(job)
    row.show()
    app.processEvents()
    return row


def test_running_row_shows_its_own_progress():
    row = running_row()
    assert row.bar.isVisible()
    assert row.figure.text() == "39%"
    assert row.status.text()


def test_row_on_stage_keeps_only_title_and_state():
    row = running_row()
    row.set_on_stage(True)
    assert not row.bar.isVisible()
    assert not row.figure.isVisible()
    assert row.status.text() == ""
    assert row.title.text() == "Big Buck Bunny"
    assert row.state.text() == "скачивается"


# ----- Цифры: моноширинные, чтобы проценты и длительности не прыгали -------

def test_figures_use_tabular_digits():
    from PySide6.QtGui import QFontMetricsF

    metrics = QFontMetricsF(theme.figure_font(40))
    assert metrics.horizontalAdvance("1111") == metrics.horizontalAdvance("0000")


# ----- Фрагмент: включённый режим не может молча скачать ролик целиком -----

def test_enabled_fragment_is_visible_and_reaches_the_download_request(tmp_path, monkeypatch):
    class Worker:
        def cancel(self):
            pass

    monkeypatch.setattr(MainWindow, "_check_environment", lambda self: None)
    monkeypatch.setattr(MainWindow, "_start_worker", lambda self, job: Worker())
    window = MainWindow(tmp_path)
    window.settings["out_dir"] = str(tmp_path / "out")
    window.preview = Preview(
        url="https://youtu.be/test", kind="video", title="test", uploader="",
        duration=60, thumbnail_url=None, tiers=(2160, 1440, 1080, 720),
    )
    window._fill_quality()
    window._update_controls()
    window.trim_check.setChecked(True)

    assert window.download_button.text() == "скачать фрагмент"
    assert [button.text() for button in window.quality.buttons()] == ["лучшее", "1080p", "720p"]

    window._start_download()
    assert window.queue.jobs == []
    assert "начало или конец" in window.trim_error.text().lower()

    window.trim_start.setText("0:10")
    window.trim_end.setText("0:20")
    window._start_download()

    assert window.queue.jobs[0].request.trim == (10.0, 20.0)
    window._update_stage()
    assert window.progress_figure.isHidden()
    assert not window.progress_busy.isHidden()
