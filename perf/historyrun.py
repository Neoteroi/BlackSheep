"""
This script allows to execute the same performance tests on multiple
versions of BlackSheep. It creates a temporary copy of the perf folder
to ensure that the same tests are executed at various points of the
Git history.

python perf/historyrun.py --commits 82ed065 1237b1e
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)


def copy_perf_code(temp_dir):
    """
    Copies the 'perf' folder into a temporary directory to ensure the same
    performance code is used across different commits.
    """
    source_dir = os.path.abspath("perf")  # Path to the 'perf' folder
    if not os.path.exists(source_dir):
        logger.error("Source directory '%s' does not exist.", source_dir)
        sys.exit(1)

    dest_dir = os.path.join(temp_dir, "perf")

    # Copy the 'perf' folder recursively
    shutil.copytree(source_dir, dest_dir)

    logger.debug("'perf' folder copied to temporary directory: %s", dest_dir)
    return dest_dir


def restore_perf_code(temp_dir):
    logger.info("Replacing the local 'perf' folder with the backup...")

    # Path to the local 'perf' folder
    local_perf_dir = os.path.abspath("perf")

    # Delete the local 'perf' folder if it exists
    if os.path.exists(local_perf_dir):
        logger.info("Deleting the local 'perf' folder: %s", local_perf_dir)
        shutil.rmtree(local_perf_dir)

    # Path to the backup 'perf' folder in the temporary directory
    source_dir = os.path.join(temp_dir, "perf")

    # Copy the backup 'perf' folder to the current directory
    shutil.copytree(source_dir, local_perf_dir)
    logger.info("Restored 'perf' folder from backup: %s", source_dir)


@contextmanager
def gitcontext():
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], universal_newlines=True
    ).strip()
    try:
        yield branch
    except:
        # go back to the original branch
        pass
    logger.info("Returning to the original branch")
    subprocess.check_output(["git", "checkout", "-f", branch], universal_newlines=True)


def make_compile():
    logger.info("Compiling BlackSheep extensions")
    # TODO: use other commands to support Windows
    subprocess.check_output(["make", "compile"], universal_newlines=True)


def run_tests(iterations: int, output_dir: str, times: int):
    subprocess.check_output(
        [
            "python",
            "perf/main.py",
            "--iterations",
            str(iterations),
            "--output-dir",
            output_dir,
            "--times",
            str(times),
        ],
        universal_newlines=True,
    )


def copy_results(source_dir, dest_dir):
    """
    Copies all files from the source directory to the destination directory.
    If the destination directory does not exist, it is created.
    """
    if not os.path.exists(source_dir):
        logger.error("Source directory '%s' does not exist.", source_dir)
        sys.exit(1)

    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        logger.info("Created destination directory: %s", dest_dir)

    # Copy all files and subdirectories
    for item in os.listdir(source_dir):
        source_path = os.path.join(source_dir, item)
        dest_path = os.path.join(dest_dir, item)

        if os.path.isdir(source_path):
            shutil.copytree(source_path, dest_path)
        else:
            shutil.copy2(source_path, dest_path)

    logger.info("Copied all files from '%s' to '%s'", source_dir, dest_dir)


def main():
    parser = argparse.ArgumentParser(description="BlackSheep Performance Benchmarking")
    parser.add_argument(
        "--iterations", type=int, default=1000000, help="Number of iterations"
    )
    parser.add_argument(
        "--times", type=int, default=5, help="How many runs for each commit"
    )
    parser.add_argument(
        "--commits",
        type=str,
        nargs="+",  # Accept one or more commit SHAs
        help="List of Git commit SHAs to benchmark",
    )
    args = parser.parse_args()

    # Example usage of the commits argument
    if args.commits:
        print(f"Commits to benchmark: {args.commits}")
    else:
        print("No commits provided.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "results"
        copy_perf_code(temp_dir)

        with gitcontext():
            for commit in args.commits:
                subprocess.check_output(
                    ["git", "checkout", "-f", commit], universal_newlines=True
                )
                logger.info("Checked out commit: %s", commit)
                make_compile()
                restore_perf_code(temp_dir)
                run_tests(args.iterations, str(output_dir), args.times)

        # Copy the results from output_dir to ./benchmark_results
        copy_results(str(output_dir), "./benchmark_results")


if __name__ == "__main__":
    main()
