#!/usr/bin/env python

"""Visualize the results of full_benchmark.py."""

import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import pandas as pd


def clear_unnamed_labels(name: str) -> str:
    return "" if name.startswith("Unnamed: ") else name


def main() -> None:
    """Main function."""
    data: pd.DataFrame = pd.read_csv(
        sys.stdin,
        comment="#",
        sep="\t",
        header=[0, 1],
        index_col=0,
        dtype=defaultdict(
            lambda: "float64",
            {
                ("status", "Unnamed: 11_level_1"): pd.CategoricalDtype(
                    categories=pd.Index(["ok", "emfile", "timeout"], dtype="string"),
                    ordered=False,
                ),
                ("n_files", "Unnamed: 12_level_1"): "int64",
                ("n_parallel", "Unnamed: 13_level_1"): "int64",
            },
        ),
    ).rename(columns=clear_unnamed_labels, level=1)
    ax: plt.Axes
    fig, ax = plt.subplots(1, 1)
    for n, s in data.groupby("n_files"):
        assert isinstance(n, int)
        assert isinstance(s, pd.DataFrame)
        if not (n // 100) % 2:
            continue
        section = s.set_index("n_parallel")["time_ms"].rename_axis(columns="time_ms")
        section.plot(
            y="median",
            yerr="std",
            ax=ax,
            capsize=4,
            label=n,
            grid=True,
            xlabel="Worker pool size",
            ylabel="Median load time [ms]",
            legend=False,
        )
    ax.legend(
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
        title="Number of files",
        reverse=True,
    )
    ax.set_ylim(bottom=0.0)
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
