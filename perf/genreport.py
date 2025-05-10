"""
Generate an Excel report to compare benchmark results across commits.
"""

from pathlib import Path
import argparse
import glob
import json
import os

import matplotlib.pyplot as plt
import pandas as pd


def _match_filter(data, python_filter: str, platform_filter: str):
    if python_filter or platform_filter:
        system_info = data["system_info"]
        if python_filter and python_filter not in system_info["python_version"]:
            return False
        if platform_filter and platform_filter not in system_info["platform"]:
            return False
    return True


def load_results(
    results_dir="benchmark_results",
    python_filter: str = "",
    platform_filter: str = "",
):
    """Load all benchmark results from the directory"""
    results = []
    for filename in glob.glob(f"{results_dir}/blacksheep_perf_*.json"):
        with open(filename, "r") as f:
            data = json.load(f)
            if not _match_filter(data, python_filter, platform_filter):
                continue
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
            "python_version": result.get("system_info", {}).get(
                "python_version", "unknown"
            ),
            "platform": result.get("system_info", {}).get("platform", "unknown"),
            "branch": result.get("git_info", {}).get("branch", "unknown"),
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
    aggregated_df = df.groupby(by.split(), as_index=False).agg(aggregation_functions)

    # Reorder columns to match the original DataFrame
    aggregated_df = aggregated_df[
        [col for col in df.columns if col in aggregated_df.columns]
    ]

    # Sort by the 'date' column
    aggregated_df = aggregated_df.sort_values(by=["date", "python_version", "platform"])

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
                "categories": f"=results!$B$2:$E${(max_row + 1)}",
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
    chart.set_title({"name": "Performance comparison (lower is better)"})
    chart.set_x_axis({"name": ""})
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
                "categories": f"=results!$B$2:$E${(max_row + 1)}",
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
    chart.set_title({"name": "Mem usage comparison (lower is better)"})
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


def _set_number_format(workbook, worksheet, df):
    # Set number format for columns with "avg_ms" or "peak_mb" in their header
    number_format = workbook.add_format(
        {"num_format": "0.00000000", "align": "left"}
    )  # 8 decimal points
    for col in df.columns:
        if "avg_ms" in col or "peak_mb" in col:
            col_index = df.columns.get_loc(col)  # Get the column index
            col_letter = chr(65 + col_index)  # Convert column index to Excel letter
            worksheet.set_column(f"{col_letter}:{col_letter}", None, number_format)


def write_excel(df, output_file_name: str):
    if not output_file_name.endswith(".xlsx"):
        output_file_name = output_file_name + ".xlsx"
    k = 0
    orig_name = output_file_name
    while Path(output_file_name).exists():
        k += 1
        output_file_name = orig_name.replace(".xlsx", f"-{k}.xlsx")

    # Export to Excel for further analysis
    writer = pd.ExcelWriter(output_file_name, engine="xlsxwriter")
    df.to_excel(writer, index=False, sheet_name="results")

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets["results"]
    _set_number_format(workbook, worksheet, df)

    # Get the dimensions of the dataframe.
    (max_row, max_col) = df.shape

    # Add a table to the worksheet
    worksheet.add_table(
        f"A1:{chr(65 + max_col - 1)}{max_row + 1}",
        {
            "columns": [{"header": col} for col in df.columns],
            "style": "Table Style Medium 9",
        },
    )
    # Configure the first series.
    # Plot time metrics

    _add_charts(workbook, df, worksheet, max_row)
    _set_conditional_formatting(df, worksheet, max_row)

    # Close the Pandas Excel writer and output the Excel file.
    worksheet.autofit()
    writer.close()
    print(f"XLSX saved to {output_file_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare BlackSheep benchmark results")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="./benchmark_results",
        help="Directory containing benchmark results",
    )
    parser.add_argument(
        "--group-by",
        type=str,
        default="commit python_version platform",
        help="Group by",
    )
    parser.add_argument(
        "--python",
        type=str,
        default="",
        help="Filter by Python version",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="",
        help="Filter by platform",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="performance-comparison.xlsx",
        help="Output file name",
    )
    args = parser.parse_args()

    results = load_results(args.results_dir, args.python, args.platform)
    if not results:
        print(f"No benchmark results found in {args.results_dir}")
        exit(0)

    df = create_comparison_table(results)
    df = _aggregate(df, args.group_by)
    write_excel(df, args.output)
