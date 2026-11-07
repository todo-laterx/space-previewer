#!/usr/bin/env python3
"""Compatibility entry point: Nautilus by default, standalone with its flag."""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from app import SpacePreviewerApp


def create_app(standalone=False):
    if standalone:
        return SpacePreviewerApp()
    from integrations.nautilus import NautilusIntegration
    return SpacePreviewerApp(integration=NautilusIntegration())


def main():
    args = list(sys.argv)
    standalone = len(args) > 1 and args[1] == "--standalone"
    if standalone:
        del args[1]
    return create_app(standalone=standalone).run(args)


if __name__ == "__main__":
    sys.exit(main())
