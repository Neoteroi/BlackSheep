import gc
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TypedDict
import cProfile
import pstats
import io


class BenchmarkResult(TypedDict):
    total_time: float
    avg_time: float
    iterations: int


@dataclass
class TimerResult:
    elapsed_time: float


@contextmanager
def timer():
    result = TimerResult(-1)
    start_time = time.perf_counter()  # Use perf_counter for high-resolution timing
    yield result
    end_time = time.perf_counter()
    result.elapsed_time = end_time - start_time


async def async_benchmark(func, iterations: int) -> BenchmarkResult:
    # warmup
    warmup_iterations = max(1, min(100, iterations // 10))
    for _ in range(warmup_iterations):
        await func()

    # Collect garbage to ensure fair comparison
    gc.collect()

    # actual timing
    with timer() as result:
        for _ in range(iterations):
            await func()

    return {
        "total_time": result.elapsed_time,
        "avg_time": result.elapsed_time / iterations,
        "iterations": iterations,
    }


def sync_benchmark(func, iterations: int) -> BenchmarkResult:
    # warmup
    warmup_iterations = max(1, min(100, iterations // 10))
    for _ in range(warmup_iterations):
        func()

    # Collect garbage to ensure fair comparison
    gc.collect()

    # actual timing
    with timer() as result:
        for _ in range(iterations):
            func()

    return {
        "total_time": result.elapsed_time,
        "avg_time": result.elapsed_time / iterations,
        "iterations": iterations,
    }


async def profile_benchmark(func, iterations, is_async, top=50):
    pr = cProfile.Profile()
    if is_async:
        pr.enable()
        await func()
        pr.disable()
    else:
        pr.enable()
        func(iterations)
        pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    # Sort stats by cumulative time (ct) descending
    sorted_stats = sorted(
        ps.stats.items(),  # type: ignore
        key=lambda item: item[1][3],  # item[1][3] is cumtime
        reverse=True,
    )

    stats_list = []
    for i, (func_tuple, stat) in enumerate(sorted_stats):
        if i == top:
            break
        i += 1
        filename, lineno, funcname = func_tuple
        cc, nc, tt, ct, callers = stat
        stats_list.append(
            {
                "filename": filename,
                "lineno": lineno,
                "function": funcname,
                "callcount": cc,
                "reccallcount": nc,
                "tottime": tt,
                "cumtime": ct,
                "callers": list(callers),
            }
        )
    return stats_list


def main_run(func):
    """
    Run the benchmark function and print the results.

    To use with iPython:
    PYTHONPATH="." ipython perf/benchmarks/filename.py timeit

    To use with asyncio:
    PYTHONPATH="." ipython perf/benchmarks/filename.py
    """
    import asyncio
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "timeit":
        from IPython import get_ipython

        ipython = get_ipython()
        if ipython:
            ipython.run_line_magic("timeit", f"asyncio.run({func.__name__}(1))")
        else:
            print("ERROR: Use iPython to run the benchmark with timeit.")
            sys.exit(1)
    else:
        asyncio.run(func())
