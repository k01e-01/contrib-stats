#!/usr/bin/env python3

import argparse
import sys
import os
import io
import toml
import json
import csv
import signal
from typing import Any
from dotenv import load_dotenv
from github import Github, Auth, GithubException
from datetime import datetime
from rich.pretty import pprint  # pyright: ignore
from rich.console import Console
from rich.control import Control


# https://github.com/k01e-01/contrib-stats

# -- contrib-stats --
# author: k01e-01
# license: MIT
# updated: 2024-05-20

# built for @keiranm

# see DEFAULT_INPUT and --help for usage information
# alternatively, ask @keiranm or @k01e-01

# deps: argparse, toml, python-dotenv, pygithub, rich
# ver: python 3.11


DEFAULT_INPUT = """
env = ".env"

[default]

[[stats]]
label = "vencord"
repos = [ "Vendicated/Vencord" ]
filetypes = [ "ts" ]
start_date = 2024-01-01T00:00:00Z
end_date = 2024-02-01T00:00:00Z
"""

silent: bool = False
console = Console()
_tempprint = console.print  # hhhh forgive me
_temppprint = pprint


def print(*args, **kwargs):
    global silent
    if not silent:
        _tempprint(*args, **kwargs)


def pprint(*args, **kwargs):
    global silent
    if not silent:
        _temppprint(*args, **kwargs)


# try to get the item from all provided dicts
# otherwise return default
def trygetitem(tables: list[dict[str, Any]], item: str, default: Any) -> Any:
    for table in tables:
        try:
            return table[item]
        except KeyError:
            continue
    return default


# if item is already in the dict, add value onto it
# otherwise, create new item with value
def addornewitem(table: dict[str, int], item: str, value: int):
    try:
        table[item] += value
    except KeyError:
        table[item] = value


def parse_args():
    parser = argparse.ArgumentParser(prog="contrib-stats")
    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        help="do not output verbose information to stdout",
    )
    parser.add_argument(
        "-i",
        "--input",
        default="-",
        help="input toml file (or default if none/'-' specified)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="output toml file (or stdout if none/'-' specified)",
    )

    args = parser.parse_args()

    return args


def open_files(args):
    if args.input == "-":
        print("no input file provided, using default!", style="bold white on red")

        # input_file needs to be a TextIOWrapper, so we do this yuckyness
        binary_stream = io.BytesIO()
        input_file = io.TextIOWrapper(binary_stream)
        input_file.write(DEFAULT_INPUT)
        input_file.flush()
        binary_stream.seek(0)
    else:
        try:
            input_file = open(args.input, "r")
        except OSError as e:
            print(f"could not open input file: {e}", style="bold white on red")
            exit(1)

    if args.output == "-":
        output_file = sys.stdout
    else:
        try:
            output_file = open(args.output, "w+")
        except OSError as e:
            print(f"could not open output file: {e}", style="bold white on red")
            exit(2)

    return (input_file, output_file)


def get_github():
    github_token = os.environ.get("GITHUB_AUTH_TOKEN")

    if github_token is None:
        print(
            "using no api token is not recomended, you will get ratelimited!",
            style="bold white on red",
        )
        github = Github()
    else:
        github_auth = Auth.Token(github_token)
        github = Github(auth=github_auth)

    return github


def print_filechange(filename, author, changes):
    print(
        f"file '{filename}' \
by '{author}' \
with {changes} changes"
    )


def filetype_check(output_filename, stats_count):
    if output_filename == "-":
        return

    extension = output_filename.split(".")[-1]

    if extension == "csv" and stats_count > 1:
        # csv is annoying to work lol
        print(
            "only the last 'stats' will make it to the output!",
            style="bold white on red",
        )

    if not extension in ["toml", "json", "csv"]:
        print(
            "unsupported filetype, you will get a python object output!",
            style="bold white on red",
        )


def write_output(
    output: dict[str, dict[str, int]],
    output_file,
    output_filename: str,
    first_stat,
):
    extension = output_filename.split(".")[-1]

    if extension == "toml":
        output_file.write(toml.dumps(output))

    elif extension == "json":
        output_file.write(json.dumps(output))

    elif extension == "csv":
        csv_file = csv.writer(output_file)
        csv_file.writerow(["user", "contrib"])

        for key, val in output[first_stat].items():
            csv_file.writerow([key, str(val)])

    else:
        # __repr__ is what the print() function uses
        output_file.write(output.__repr__())


def handle_signal(*_):
    console.control(Control.move_to_column(0))
    print("caught ^C, exiting gracefully!", style="bold white on red")
    exit(0)


def main():
    signal.signal(signal.SIGINT, handle_signal)

    args = parse_args()

    global silent
    silent = args.silent

    input_file, output_file = open_files(args)

    try:
        input_data = toml.loads(input_file.read())
    except toml.TomlDecodeError as e:
        print(f"could not decode toml: {e}", style="bold white on red")
        exit(3)

    filetype_check(args.output, len(trygetitem([input_data], "stats", [])))

    try:
        load_dotenv(input_data["env"])
    except KeyError as _:
        pass

    github = get_github()

    default = trygetitem([input_data], "default", {})
    output = {}

    print("[bold]starting![/bold]")

    label = ""

    for stat in trygetitem([input_data], "stats", []):
        trytables = [stat, default]

        label = trygetitem(trytables, "label", "")
        repos = trygetitem(trytables, "repos", [])
        filetypes = trygetitem(trytables, "filetypes", [])
        start = trygetitem(trytables, "start_date", datetime.fromtimestamp(0))
        end = trygetitem(trytables, "end_date", datetime.now())

        print(f"[bold blue]processing:[/bold blue] {label}")

        authors = {}

        for repo_str in repos:
            print(f"[bold blue]processing repo:[/bold blue] {repo_str}")
            try:
                repo = github.get_repo(repo_str)
            except GithubException as _:
                print(f"unable to get {repo_str}", style="bold white on red")
                exit(4)

            for commit in repo.get_commits(since=start, until=end):
                # not even sure how a commit can have no author!
                if commit.author is None:
                    continue
                if commit.author.name is None:
                    continue

                for file in commit.files:
                    if not file.filename.split(".")[-1] in filetypes:
                        continue

                    print_filechange(
                        file.filename,
                        commit.author.name,
                        file.changes,
                    )

                    addornewitem(authors, commit.author.name, file.changes)

        output[label] = authors

    print("[bold]done![/bold] output:")
    print(output)

    write_output(
        output,
        output_file,
        args.output,
        label,
    )

    # close everything, leaving files open is bad practice
    input_file.close()
    output_file.close()
    github.close()
    return


if __name__ == "__main__":
    main()
    exit(0)
