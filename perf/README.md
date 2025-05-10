# Benchmark

This folder contains scripts to benchmark the performance of the library. The
purpose of these benchmarks is to measure how changes in code affect
performance, across Git commits, Python versions, and operating system.

Benchmarks measure execution time and memory utilization.

> [!TIP]
>
> Download the results from the GitHub Workflow.
> The `benchmark-reports` artifacts include Excel files with tables and charts.
>
>  [![Build](https://github.com/Neoteroi/BlackSheep/workflows/Benchmark/badge.svg)](https://github.com/Neoteroi/BlackSheep/actions/workflows/perf.yml)

The code can both collect information and compare it depending on the Git
commit SHA.

```bash
pip install -r req.txt
```

From the root folder:

```bash
# Run the benchmark suite
export PYTHONPATH="."

python perf/main.py

# To run more than onces:
python perf/main.py --times 3

# Generate XLSX report
python perf/genreport.py
```

Run to generate results from different points in history:

```bash
python perf/historyrun.py --commits 82ed065 1237b1e
```

## Code organization

Benchmarks are organized in such way that each file can be run interactively using
**iPython**, but are also automatically imported by `main.py` following the convention
that benchmark functions have names starting with `benchmark_`.

To run a single benchmark using **iPython**, or [`cProfile`](https://docs.python.org/3.13/library/profile.html#profile-cli):

```bash
export PYTHONPATH="."

ipython perf/benchmarks/writeresponse.py timeit

python -m cProfile -s tottime perf/benchmarks/writeresponse.py | head -n 50
```

## Debugging with Visual Studio Code

To debug specific files with VS Code, use a `.vscode\launch.json` file like:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python Debugger: Current File",
            "type": "debugpy",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        }
    ]
}
```

## When modifying benchmark code

```bash
export PYTHONPATH="."
rm -rf benchmark_results && python perf/main.py && python perf/genreport.py
```
