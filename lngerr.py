
import sys
from rich.console import Console


conerr = Console(stderr=True, highlight=False)


def format_tab_ptr(s: str, ptr):
	return s.expandtabs(4), len(s[:ptr].expandtabs(4))


def generic_error(msg, poses, srcs: dict):
	conerr.print(f"[red bold]<!>[/red bold] [red]{msg}[red]")

	for ln, co, fi in poses:
		conerr.print(f"  [red]at {fi}:{ln}:{co}[/red]")

		src = srcs.get(fi)
		if src is None: continue

		lines = src.split("\n")
		if not (1 <= ln <= len(lines)): continue

		raw = lines[ln - 1]
		shown, at = format_tab_ptr(raw, co - 1)
		conerr.print(shown)
		conerr.print(f"{" " * at}[red bold]^[/red bold]")

	sys.exit(1)
