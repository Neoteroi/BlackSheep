"""Compare benchmark results across commits"""

import argparse
import glob
import json
import os

import matplotlib.pyplot as plt
import pandas as pd


def load_results(results_dir="./benchmark_results"):
    """Load all benchmark results from the directory"""
    results = []
    for filename in glob.glob(f"{results_dir}/blacksheep_perf_*.json"):
        with open(filename, "r") as f:
            data = json.load(f)
            data["filename"] = os.path.basename(filename)
            results.append(data)

    # Sort by commit date
    results.sort(key=lambda x: x.get("git_info", {}).get("commit_date", ""))
    return results


def create_comparison_table(results):
    """Create a pandas DataFrame for comparison"""
    rows = []
    for result in results:
        commit = result.get("git_info", {}).get("commit_hash", "unknown")[:8]
        date = result.get("git_info", {}).get("commit_date", "unknown")

        row = {
            "timestamp": result.get("timestamp", "unknown"),
            "commit": commit,
            "date": date,
            "branch": result.get("git_info", {}).get("branch", "unknown"),
            "python_version": result.get("system_info", {}).get(
                "python_version", "unknown"
            ),
            "platform": result.get("system_info", {}).get("platform", "unknown"),
        }

        # Add benchmark results
        for benchmark_name, benchmark_data in result.get("benchmarks", {}).items():
            row[f"{benchmark_name}_avg_ms"] = benchmark_data.get("avg_time", 0) * 1000

        # Add memory results
        for mem_name, mem_data in result.get("memory_benchmarks", {}).items():
            row[f"{mem_name}_peak_mb"] = mem_data.get("peak", 0)

        rows.append(row)

    return pd.DataFrame(rows)


def plot_performance_trends(df, output_file="performance_trends.png"):
    """Create a plot showing performance trends"""
    plt.figure(figsize=(12, 8))

    # Plot time metrics
    time_cols = [col for col in df.columns if col.endswith("_avg_ms")]
    for col in time_cols:
        plt.subplot(2, 1, 1)
        plt.plot(df["date"], df[col], marker="o", label=col)

    plt.title("Performance Trends Across Commits")
    plt.ylabel("Time (ms)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True)

    # Plot memory metrics
    mem_cols = [col for col in df.columns if col.endswith("_peak_mb")]
    for col in mem_cols:
        plt.subplot(2, 1, 2)
        plt.plot(df["date"], df[col], marker="s", label=col)

    plt.ylabel("Memory (MB)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Plot saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare BlackSheep benchmark results")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="./benchmark_results",
        help="Directory containing benchmark results",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="performance_trends.png",
        help="Output file for performance trends plot",
    )
    args = parser.parse_args()

    results = load_results(args.results_dir)
    if not results:
        print(f"No benchmark results found in {args.results_dir}")
        exit(1)

    df = create_comparison_table(results)
    print("Performance comparison:")
    print(df.to_string())

    plot_performance_trends(df, args.output)

    # Export to CSV for further analysis
    csv_file = "performance_comparison.csv"
    df.to_csv(csv_file, index=False)
    print(f"CSV export saved to {csv_file}")
