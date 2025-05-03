"""
BlackSheep performance benchmarking suite.
Refer to the README for details.
"""

import argparse
import asyncio
import gc
import importlib
import inspect
import json
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psutil
from memory_profiler import memory_usage


def collect_benchmark_functions(package_name: str):
    """
    Collects all functions whose names start with 'benchmark_' from the modules
    inside the specified package.

    Args:
        package_name (str): The name of the package to search for benchmark functions.

    Returns:
        dict: A dictionary where keys are function names and values are the function objects.
    """
    benchmark_functions = {}
    package_path = Path(__file__).parent / package_name

    if not package_path.exists() or not package_path.is_dir():
        raise ValueError(f"Package '{package_name}' not found at {package_path}")

    # Iterate over all Python files in the package
    for module_path in package_path.glob("*.py"):
        module_name = f"{package_name}.{module_path.stem}"
        module = importlib.import_module(module_name)

        # Inspect the module for functions starting with 'benchmark_'
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("benchmark_"):
                # Strip the prefix
                benchmark_functions[name[10:]] = func

    return benchmark_functions


# Memory profiling wrapper
def get_memory_usage(func, *args, **kwargs):
    def wrapper():
        if asyncio.iscoroutinefunction(func):
            # Check if an event loop is already running
            try:
                loop = asyncio.get_running_loop()
                return loop.create_task(func(*args, **kwargs))
            except RuntimeError:
                # If no loop is running, use `asyncio.run`
                return asyncio.run(func(*args, **kwargs))
        else:
            return func(*args, **kwargs)

    # Force garbage collection before measuring
    gc.collect()
    mem_usage = memory_usage(wrapper, interval=0.01, timeout=30)

    return {
        "peak": max(mem_usage),
        "avg": statistics.mean(mem_usage),
        "min": min(mem_usage),
        "samples": len(mem_usage),
    }


def get_git_info():
    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], universal_newlines=True
        ).strip()
        commit_date = subprocess.check_output(
            ["git", "show", "-s", "--format=%ci", commit_hash], universal_newlines=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], universal_newlines=True
        ).strip()

        return {
            "commit_hash": commit_hash,
            "commit_date": commit_date,
            "branch": branch,
        }
    except subprocess.CalledProcessError:
        return {"error": "Not a git repository or git not available"}


# Get system information
def get_system_info():
    return {
        "cpu_count": os.cpu_count(),
        "memory_total": psutil.virtual_memory().total,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }


async def run_all_benchmarks(iterations: int, key: str):
    results = {
        "timestamp": datetime.now().isoformat(),
        "git_info": get_git_info(),
        "system_info": get_system_info(),
        "benchmarks": {},
        "memory_benchmarks": {},
    }

    # Collect all benchmark functions
    benchmark_functions = collect_benchmark_functions("benchmarks")
    print(f"Found {len(benchmark_functions)} benchmarks.")

    # Time benchmarks
    for name, func in benchmark_functions.items():
        if key and key not in name:
            continue

        print(f"Running benchmark: {name}...")
        if asyncio.iscoroutinefunction(func):
            results["benchmarks"][name] = await func(iterations)
        else:
            results["benchmarks"][name] = func(iterations)

    # Memory benchmarks
    for name, func in benchmark_functions.items():
        if key and key not in name:
            continue

        print(f"Running memory benchmark: {name}...")
        results["memory_benchmarks"][name] = get_memory_usage(func, iterations)

    return results


def save_results(results, output_dir="./benchmark_results"):
    Path(output_dir).mkdir(exist_ok=True)

    # Generate a filename with git hash and timestamp
    git_hash = results["git_info"].get("commit_hash", "no-git")[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # TODO: filename should also depend on the python version
    # and the platform (e.g., linux, windows, macos)
    filename = f"{output_dir}/blacksheep_perf_{git_hash}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {filename}")
    return filename


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlackSheep Performance Benchmarking")
    parser.add_argument(
        "--iterations", type=int, default=100000, help="Number of iterations"
    )
    parser.add_argument(
        "--output-dir", type=str, default="./benchmark_results", help="Output directory"
    )
    parser.add_argument(
        "--filter",
        "-f",
        type=str,
        default="",
        help="Optional filter to run specific benchmarks",
    )
    args = parser.parse_args()

    results = asyncio.run(run_all_benchmarks(args.iterations, args.filter))
    save_results(results, args.output_dir)
