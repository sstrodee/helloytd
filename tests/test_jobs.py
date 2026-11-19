from app.jobs import Job, JobQueue


class FakeWorker:
    def __init__(self, job):
        self.job = job
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class Starter:
    def __init__(self):
        self.workers = []

    def __call__(self, job):
        worker = FakeWorker(job)
        self.workers.append(worker)
        return worker


def make_queue():
    starter = Starter()
    return JobQueue(starter), starter


def job(title):
    return Job(title=title, request=None)


class TestQueue:
    def test_first_job_starts_right_away(self):
        queue, starter = make_queue()
        first = queue.add(job("a"))
        assert [worker.job for worker in starter.workers] == [first]
        assert first.state == "running"

    def test_next_job_waits_for_the_running_one(self):
        queue, starter = make_queue()
        queue.add(job("a"))
        second = queue.add(job("b"))
        assert len(starter.workers) == 1
        assert second.state == "queued"

    def test_finishing_starts_the_next_job(self):
        queue, starter = make_queue()
        first = queue.add(job("a"))
        second = queue.add(job("b"))
        queue.finish(first.id, ok=True, path="C:/a.mp4")
        assert first.state == "done"
        assert first.path == "C:/a.mp4"
        assert starter.workers[-1].job is second
        assert second.state == "running"

    def test_failure_does_not_block_the_queue(self):
        queue, starter = make_queue()
        first = queue.add(job("a"))
        second = queue.add(job("b"))
        queue.finish(first.id, ok=False, message="нет сети")
        assert first.state == "failed"
        assert first.message == "нет сети"
        assert second.state == "running"

    def test_cancelled_queued_job_never_starts(self):
        queue, starter = make_queue()
        first = queue.add(job("a"))
        second = queue.add(job("b"))
        queue.cancel(second.id)
        queue.finish(first.id, ok=True)
        assert second.state == "cancelled"
        assert len(starter.workers) == 1

    def test_cancelling_running_job_stops_its_worker_then_moves_on(self):
        queue, starter = make_queue()
        first = queue.add(job("a"))
        second = queue.add(job("b"))
        queue.cancel(first.id)
        assert starter.workers[0].cancelled is True
        queue.finish(first.id, ok=False, message="остановлено")
        assert first.state == "cancelled"
        assert second.state == "running"

    def test_failed_job_can_be_retried(self):
        queue, starter = make_queue()
        first = queue.add(job("a"))
        queue.finish(first.id, ok=False, message="нет сети")
        queue.retry(first.id)
        assert first.state == "running"
        assert first.message is None
        assert len(starter.workers) == 2

    def test_ids_are_unique(self):
        queue, _ = make_queue()
        assert queue.add(job("a")).id != queue.add(job("b")).id

    def test_success_can_carry_a_note(self):
        queue, _ = make_queue()
        first = queue.add(job("a"))
        queue.finish(first.id, ok=True, message="Скачано 2 из 3", path="C:/List")
        assert first.state == "done"
        assert first.message == "Скачано 2 из 3"

    def test_forgetting_finished_keeps_active_jobs(self):
        queue, _ = make_queue()
        first = queue.add(job("a"))
        second = queue.add(job("b"))
        queue.finish(first.id, ok=True)
        third = queue.add(job("c"))
        queue.forget_finished()
        assert queue.jobs == [second, third]
