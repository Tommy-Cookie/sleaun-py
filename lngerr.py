
import sys
from rich.console import Console


conerr = Console(stderr=True, highlight=False)


def format_tab_ptr(string: str, ptr: int) -> tuple:
	orig = string[:ptr]
	seg = orig.replace("\t", "    ")
	offset = len(seg) - len(orig)

	return string.replace("\t", "    "), ptr + offset


def generic_error(msg, poses, src: str):
	conerr.print(f"[red bold]<!>[/red bold] [red]{msg}[red]")

	lines = src.split("\n")
	for p in poses:
		conerr.print(f"  [red]at {p[2]}:{p[0]}:{p[1]}[/red]")
		fmt, at = format_tab_ptr(lines[p[0] - 1], p[1] - 1)
		conerr.print(fmt)
		conerr.print(f"{" " * at}[red bold]^[/red bold]")

	sys.exit(1)
