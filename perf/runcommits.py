"""
This script allows to execute the same performance tests on multiple
versions of BlackSheep.

python perf/runcommits.py --commits 935754 eb1564 9e4246
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager

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


@contextmanager
def gitcontext():
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], universal_newlines=True
    ).strip()
    try:
        yield branch
    except:
        # go back to the original branch
        logger.info("Returning to the original branch")
        subprocess.check_output(["git", "checkout", branch], universal_newlines=True)


def make_compile():
    # TODO: use other commands to support Windows
    subprocess.check_output(["make", "compile"], universal_newlines=True)


def run_tests():
    subprocess.check_output(["python", "perf/main.py"], universal_newlines=True)


def main():
    parser = argparse.ArgumentParser(description="BlackSheep Performance Benchmarking")
    parser.add_argument(
        "--iterations", type=int, default=100000, help="Number of iterations"
    )
    parser.add_argument(
        "--output-dir", type=str, default="./benchmark_results", help="Output directory"
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

    with tempfile.TemporaryDirectory() as dest_folder:
        copy_perf_code(dest_folder)

        # Delete the local perf folder and replace it with the backup one

        with gitcontext():
            for commit in args.commits:
                subprocess.check_output(
                    ["git", "checkout", commit], universal_newlines=True
                )
                logger.info("Checked out commit: %s", commit)
                make_compile()


if __name__ == "__main__":
    main()
