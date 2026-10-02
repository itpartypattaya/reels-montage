# -*- coding: utf-8 -*-
"""Run a command of the optional online add-on (it-reelsmaker-online) through the core.

The core is the only entry point: it finds the add-on (env REELS_ONLINE_SCRIPTS or it-reelsmaker.json ->
online_scripts, written by the add-on's link command) and runs one of its commands. Without the add-on this script
says so and exits; editing continues with local sources.

    python scripts/addon.py                       # is the add-on linked, and which commands it has
    python scripts/addon.py <command> [args...]   # for example: addon.py memes search "facepalm"
"""
import importlib, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import online, utf8_stdio


def main():
    utf8_stdio()
    ext = online()
    args = sys.argv[1:]
    if not ext:
        sys.exit("the online add-on is not installed or not linked to this project. Install it-reelsmaker-online and run "
                 "its link command in the project folder: python <add-on scripts>/reels_online.py link")
    commands = dict(getattr(ext, "COMMANDS", {}) or {})
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("add-on: " + str(Path(ext.__file__).parent))
        print("commands: " + (", ".join(sorted(commands)) or "none"))
        return
    name = args[0]
    if name not in commands:
        sys.exit(f"unknown add-on command {name!r}; available: {', '.join(sorted(commands)) or 'none'}")
    importlib.import_module(commands[name]).main(args[1:])


if __name__ == "__main__":
    main()
