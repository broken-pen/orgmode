#!/usr/bin/env python

"""Main runner of the entire benchmark."""

import argparse
import io
import shutil
import subprocess
import sys
from math import nan
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, TextIO

import pandas as pd


class TooManyFilesError(subprocess.CalledProcessError):
    """Neovim failed due to EMFILE error."""


class OpenTuple(tuple):
    """Tuple whose `str()` doesn't add parentheses."""

    __slots__ = ()

    def __str__(self) -> str:
        return ", ".join(map(repr, self))


class SameAsFiles(tuple):
    """Falsey type with a useful representation for `argparse`."""

    __slots__ = ()

    def __str__(self) -> str:
        return "same as --files-range"


def get_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    description, _, epilog = __doc__.partition("\n\n")
    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=argparse.FileType("r"),
        metavar="<FILE>",
        help="Write to the given file instead of stdou",
    )
    parser.add_argument(
        "-f",
        "--files-range",
        type=int,
        nargs=3,
        default=OpenTuple((0, 2000, 100)),
        metavar=("<START>", "<STOP>", "<STRIDE>"),
        help="Iterate N_FILES over this range",
    )
    parser.add_argument(
        "-p",
        "--parallel-range",
        type=int,
        nargs=3,
        default=SameAsFiles(),
        metavar=("<START>", "<STOP>", "<STRIDE>"),
        help="Iterate N_PARALLEL over this range",
    )
    parser.add_argument(
        "-w",
        "--n-warmup",
        type=int,
        default=10,
        metavar="<N>",
        help="run N times before the benchmark",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=2.0,
        metavar="<SECS>",
        help="after warmup, run benchmark this long",
    )
    parser.add_argument(
        "--nvim",
        type=str,
        default=shutil.which("nvim"),
        metavar="<PATH>",
        help="use this nvim executable",
    )
    return parser


def gendir(dir_: Path, n_files: int) -> None:
    """Run :code:`bash gendir.sh DIR N_FILES`."""
    for i in range(1, 1 + n_files):
        file = dir_ / f"{i}.org"
        file.touch()


def make_empty_data() -> pd.DataFrame:
    """Return a row to use in case of EMFILE."""
    data_point = pd.Series([nan, nan], index=["setup_ms", "time_ms"])
    return pd.DataFrame(3 * [data_point])


def benchmark_dir(
    nvim: str, dir_: Path, n_parallel: int, n_warmup: int, duration: float
) -> pd.DataFrame:
    """Run :code:`nvim -l benchmark_dir.lua DIR N_PARALLEL N_WARMUP DURATION_SECS`."""
    args = [
        nvim,
        "-l",
        "benchmark_dir.lua",
        str(dir_),
        str(n_parallel),
        str(n_warmup),
        str(duration),
    ]
    proc = subprocess.run(args, capture_output=True, check=True, text=True)
    csv = pd.read_csv(io.StringIO(proc.stdout), sep="\t")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return csv


ErrorCode = Literal["ok", "emfile", "timeout"]
KNOWN_ERRORS: dict[ErrorCode, str] = {
    "emfile": "EMFILE: too many open files",
    "timeout": "promise timeout of 20000ms reached",
}


def get_known_error_code(stderr: str) -> ErrorCode | None:
    """If stderr shows an error we know how to handle, return its code."""
    head, _, _ = stderr.partition("\n")
    for code, pattern in KNOWN_ERRORS.items():
        if pattern in head:
            return code
    return None


def collect_stats(data: pd.DataFrame, stats: list[str]) -> pd.Series:
    """Turn a collection of data points into a series of stats.

    A dataframe with columns ['col1', 'col2', ...] is turned into
    a multi-indexed series. The first index level are the dataframe
    columns, the second level is the respective stat.
    """
    return (
        pd.concat([getattr(data, stat)(axis=0) for stat in stats], keys=stats)
        .swaplevel()
        .sort_index()
    )


def get_data_row(
    nvim: str, dir_: Path, n_files: int, n_parallel: int, n_warmup: int, duration: float
) -> pd.Series:
    """Get one row of data via `benchmark_dir()`.

    This runs the benchmark, transforms the result into a single row (by
    taking stats) and replacing it with a dummy row in case of expected
    errors.
    """
    # pylint: disable=too-many-arguments
    try:
        csv = benchmark_dir(nvim, dir_, n_parallel, n_warmup, duration)
    except subprocess.CalledProcessError as exc:
        status = get_known_error_code(exc.stderr)
        if not status:
            raise
        csv = make_empty_data()
    else:
        status = "ok"
        # Remove superfluous data, we have to do some transformations.
        assert all(csv["n_files"] == n_files), csv
        assert all(csv["n_parallel"] == n_parallel), csv
        csv.drop(columns=["n_files", "n_parallel"], inplace=True)
    result = collect_stats(csv, stats=["mean", "median", "min", "max", "std"])
    # We've reduced the CSV from a table of data to a series of stats.
    # _Now_ we can attach the non-stats data gain.
    result["status"] = status
    result["n_files"] = n_files
    result["n_parallel"] = n_parallel
    return result


def main_inner(
    nvim: str,
    files_range: range,
    parallel_range: range,
    n_warmup: int,
    duration: float,
    output: TextIO,
) -> None:
    """Main function with arguments parsed."""
    _: pd._typing.WriteBuffer[str] = output
    rows = []
    try:
        for n_files in files_range:
            with TemporaryDirectory(prefix="org_", dir=".") as name:
                dir_ = Path(name)
                gendir(dir_, n_files)
                for n_parallel in parallel_range:
                    row = get_data_row(
                        nvim, dir_, n_files, n_parallel, n_warmup, duration
                    )
                    rows.append(row)
    except Exception:
        # Save what data we can.
        if rows:
            pd.DataFrame(rows).to_csv(output, sep="\t")
        raise
    if not rows:
        raise ValueError("no data")
    pd.DataFrame(rows).to_csv(output, sep="\t", na_rep="nan")


def main(argv: list[str]) -> int:
    """Main function."""
    args = get_parser().parse_args(argv)
    if args.nvim is None:
        raise OSError("no nvim found")
    args.files_range = range(*args.files_range)
    args.parallel_range = (
        range(*args.parallel_range) if args.parallel_range else args.files_range
    )
    try:
        main_inner(**vars(args))
    except subprocess.CalledProcessError as exc:
        sys.excepthook(*sys.exc_info())
        print(30 * "-", file=sys.stderr)
        print("catured error output:", exc.stderr, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    main(sys.argv[1:])
