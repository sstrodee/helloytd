from app.jobs import Job
from app.options import DownloadRequest
from app.workers import DownloadWorker, Environment, StreamPlanPP


def test_worker_does_not_cut_a_fully_downloaded_file_afterwards():
    class YDL:
        def __init__(self):
            self.steps = []

        def add_post_processor(self, step, when="post_process"):
            self.steps.append((step, when))

    request = DownloadRequest("https://youtu.be/test", "C:/Videos", trim=(10.0, 20.0))
    worker = DownloadWorker(Job("test", request, id=1), Environment(), "firefox", "never")
    ydl = YDL()

    worker._add_steps(ydl, [])

    assert len(ydl.steps) == 1
    assert isinstance(ydl.steps[0][0], StreamPlanPP)
    assert ydl.steps[0][1] == "before_dl"
