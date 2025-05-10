"""
Generate an Excel report to compare benchmark results across commits.
"""

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


def _aggregate(df: pd.DataFrame, by: str):
    if not by:
        return df

    # Aggregate results by the specified property
    aggregation_functions = {
        col: "mean"
        for col in df.columns
        if col.endswith("_avg_ms") or col.endswith("_peak_mb")
    }
    aggregation_functions.update(
        {
            "timestamp": "first",
            "commit": "first",
            "date": "first",
            "branch": "first",
            "python_version": "first",
            "platform": "first",
        }
    )

    # Perform the aggregation
    aggregated_df = df.groupby(by, as_index=False).agg(aggregation_functions)

    # Reorder columns to match the original DataFrame
    aggregated_df = aggregated_df[
        [col for col in df.columns if col in aggregated_df.columns]
    ]

    # Sort by the 'date' column
    aggregated_df = aggregated_df.sort_values(by="date")

    return aggregated_df


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


def _set_conditional_formatting(df, worksheet, max_row):
    all_cols = [
        col for col in df.columns if col.endswith("_avg_ms") or col.endswith("_peak_mb")
    ]
    for col in all_cols:
        col_index = df.columns.get_loc(col)  # Get the column index
        col_letter = chr(
            65 + col_index
        )  # Convert column index to Excel letter (A, B, C, etc.)
        worksheet.conditional_format(
            f"{col_letter}2:{col_letter}{max_row + 1}",
            {
                "type": "3_color_scale",
                "min_type": "min",  # Minimum value
                "min_color": "#63BE7B",  # Green for lower values
                "mid_type": "percentile",  # Midpoint as 50th percentile
                "mid_value": 50,
                "mid_color": "#FFEB84",  # Yellow for midpoint
                "max_type": "max",  # Maximum value
                "max_color": "#F8696B",  # Red for higher values
            },
        )


def _add_ms_chart(workbook, df, worksheet, max_row):
    time_cols = [col for col in df.columns if col.endswith("_avg_ms")]

    chart = workbook.add_chart({"type": "line"})  # type: ignore

    for col in time_cols:
        col_index = df.columns.get_loc(col)  # Get the column index for the series
        chart.add_series(
            {
                "name": col,
                "categories": f"=results!$B$2:$C${(max_row + 1)}",
                "values": [
                    "results",
                    1,
                    col_index,
                    max_row,
                    col_index,
                ],
                "marker": {"type": "circle"},
            }
        )

    # Add a chart title and some axis labels.
    chart.set_title({"name": "Performance comparison"})
    chart.set_x_axis({"name": "commit"})
    chart.set_y_axis({"name": "avg ms"})

    # Set an Excel chart style. Colors with white outline and shadow.
    chart.set_style(10)
    chart.set_size({"width": 1024, "height": 600})

    # Insert the chart into the worksheet.
    worksheet.insert_chart(f"A{max_row + 3}", chart)


def _add_mem_chart(workbook, df, worksheet, max_row):
    mem_cols = [col for col in df.columns if col.endswith("_peak_mb")]

    chart = workbook.add_chart({"type": "line"})  # type: ignore

    for col in mem_cols:
        col_index = df.columns.get_loc(col)  # Get the column index for the series
        chart.add_series(
            {
                "name": col,
                "categories": f"=results!$B$2:$C${(max_row + 1)}",
                "values": [
                    "results",
                    1,
                    col_index,
                    max_row,
                    col_index,
                ],
                "marker": {"type": "circle"},
            }
        )

    # Add a chart title and some axis labels.
    chart.set_title({"name": "Mem usage comparison"})
    chart.set_x_axis({"name": "commit"})
    chart.set_y_axis({"name": "peak MB"})

    # Set an Excel chart style. Colors with white outline and shadow.
    chart.set_style(10)
    chart.set_size({"width": 1024, "height": 600})

    # Insert the chart into the worksheet.
    worksheet.insert_chart(f"A{max_row + 35}", chart)


def _add_charts(workbook, df, worksheet, max_row):
    _add_ms_chart(workbook, df, worksheet, max_row)
    _add_mem_chart(workbook, df, worksheet, max_row)


def write_excel(df):
    # Export to Excel for further analysis
    excel_file = "performance_comparison.xlsx"
    writer = pd.ExcelWriter(excel_file, engine="xlsxwriter")
    df.to_excel(writer, index=False, sheet_name="results")

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets["results"]

    # Get the dimensions of the dataframe.
    (max_row, _) = df.shape

    # Configure the first series.
    # Plot time metrics

    _add_charts(workbook, df, worksheet, max_row)
    _set_conditional_formatting(df, worksheet, max_row)

    # Close the Pandas Excel writer and output the Excel file.
    worksheet.autofit()
    writer.close()
    print(f"XLSX saved to {excel_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare BlackSheep benchmark results")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="./benchmark_results",
        help="Directory containing benchmark results",
    )
    parser.add_argument("--group-by", type=str, default="commit", help="Group by")
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
    df = _aggregate(df, args.group_by)
    write_excel(df)
