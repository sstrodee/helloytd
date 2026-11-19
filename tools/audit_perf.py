"""Нагрузочный прогон очереди и реального файлового хранилища в отдельной папке."""

import cProfile
import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.jobs import DONE, Job, JobQueue
from app.storage import append_history, load_history


def measure(label, count, action):
    samples = []
    cpu = time.process_time()
    start = time.perf_counter()
    for index in range(count):
        tick = time.perf_counter()
        action(index)
        samples.append(time.perf_counter() - tick)
    elapsed = time.perf_counter() - start
    samples.sort()
    return {
        "scenario": label, "count": count, "errors": 0, "seconds": round(elapsed, 3),
        "cpu_seconds": round(time.process_time() - cpu, 3),
        "operations_per_second": round(count / elapsed, 1),
        **{f"p{p}_ms": round(samples[(count * p - 1) // 100] * 1000, 4) for p in (50, 95, 99)},
    }


def workload(folder):
    for count in (300, 3000, 10000):
        queue = JobQueue(lambda _job: object())
        yield measure("enqueue", count, lambda n: queue.add(Job(str(n), None)))
        yield measure("finish", count, lambda n: queue.finish(n + 1, True))
        assert all(job.state == DONE for job in queue.jobs)
        queue.forget_finished()
        assert not queue.jobs
    history = folder / "history.json"
    yield measure("append_history", 600, lambda n: append_history(history, {"title": f"Ролик {n}"}))
    assert [entry["title"] for entry in load_history(history)] == [f"Ролик {n}" for n in range(599, 399, -1)]


def main():
    profiler = cProfile.Profile()
    with tempfile.TemporaryDirectory(prefix="audit-perf-", dir=ROOT / ".test-deps") as folder:
        for result in workload(Path(folder)):
            print(json.dumps(result), flush=True)
        tracemalloc.start()
        profiler.enable()
        list(workload(Path(folder)))
        profiler.disable()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"Python peak allocated: {peak / 1024 ** 2:.2f} MiB")
        profiler.print_stats(sort="cumulative")


if __name__ == "__main__":
    main()
