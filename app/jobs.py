"""Очередь скачиваний: качается одно, остальные ждут.

По одному — чтобы YouTube не начал ограничивать запросы и чтобы скорость
не делилась между файлами.
"""

import itertools
import heapq
from dataclasses import dataclass

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"


@dataclass(eq=False)
class Job:
    title: str
    request: object
    id: int = 0
    state: str = QUEUED
    message: str | None = None
    path: str | None = None
    thumbnail: bytes | None = None
    progress: object = None
    kind: str = "video"    # "video" | "audio" — для значка-заглушки
    detail: str = ""       # что выбрано: «1080p, субтитры», «mp3, 320 кбит/с»


class JobQueue:
    """start_worker(job) запускает скачивание и возвращает объект с методом cancel().

    О завершении воркер сообщает через finish() — из главного потока.
    """

    def __init__(self, start_worker):
        self._start_worker = start_worker
        self._ids = itertools.count(1)
        self._running = None
        self._worker = None
        self._cancel_requested = set()
        self._by_id = {}
        self._pending = []
        self.jobs = []

    @property
    def running(self):
        return self._running

    def add(self, job):
        job.id = next(self._ids)
        job.state = QUEUED
        self.jobs.append(job)
        self._by_id[job.id] = job
        heapq.heappush(self._pending, job.id)
        self._start_next()
        return job

    def finish(self, job_id, ok, message=None, path=None):
        job = self.get(job_id)
        if job is not self._running:
            return
        if job_id in self._cancel_requested and not ok:
            self._cancel_requested.discard(job_id)
            job.state, job.message = CANCELLED, None
        elif ok:
            self._cancel_requested.discard(job_id)
            # У успеха бывает пояснение: «Скачано 18 из 20 — остальные недоступны».
            job.state, job.message, job.path = DONE, message, path
        else:
            job.state, job.message = FAILED, message
        if self._running is job:
            self._running = self._worker = None
        self._start_next()

    def cancel(self, job_id):
        job = self.get(job_id)
        if job.state == QUEUED:
            job.state = CANCELLED
        elif job.state == RUNNING and self._running is job:
            # Слот освободится, когда воркер действительно остановится и вызовет finish().
            self._cancel_requested.add(job_id)
            self._worker.cancel()

    def retry(self, job_id):
        job = self.get(job_id)
        if job.state in (FAILED, CANCELLED):
            job.state, job.message, job.path, job.progress = QUEUED, None, None, None
            heapq.heappush(self._pending, job.id)
            self._start_next()

    def forget_finished(self):
        """Убрать из списка всё завершённое; то, что качается или ждёт, остаётся."""
        self.jobs = [job for job in self.jobs if job.state in (QUEUED, RUNNING)]
        self._by_id = {job.id: job for job in self.jobs}
        self._pending = [job.id for job in self.jobs if job.state == QUEUED]
        heapq.heapify(self._pending)

    def get(self, job_id):
        return self._by_id[job_id]

    def _start_next(self):
        if self._running is not None:
            return
        while self._pending:
            job = self.get(heapq.heappop(self._pending))
            if job.state == QUEUED:
                job.state = RUNNING
                self._running = job
                self._worker = self._start_worker(job)
                return
