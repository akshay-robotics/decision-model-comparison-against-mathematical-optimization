#!/usr/bin/env python3
"""Regenerate the committed SUMO network from the plain XML source files."""

from pathlib import Path
import os
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "single"


def netconvert_binary() -> str:
    try:
        import sumo
        candidate = Path(sumo.SUMO_HOME) / "bin" / "netconvert"
        if candidate.is_file():
            return str(candidate)
    except ImportError:
        pass
    home = os.environ.get("SUMO_HOME")
    if home and (Path(home) / "bin" / "netconvert").is_file():
        return str(Path(home) / "bin" / "netconvert")
    found = shutil.which("netconvert")
    if found:
        return found
    raise RuntimeError("netconvert is unavailable; install Eclipse SUMO or set SUMO_HOME")


def main() -> None:
    subprocess.run([
        netconvert_binary(),
        "--node-files", "junction.nod.xml",
        "--edge-files", "junction.edg.xml",
        "--connection-files", "junction.con.xml",
        "--output-file", "junction.net.xml",
        "--no-turnarounds", "true",
    ], check=True, cwd=SCENARIO)


if __name__ == "__main__":
    main()
