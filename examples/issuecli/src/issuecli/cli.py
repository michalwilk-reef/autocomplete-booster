import argparse
import json
import sys

import argcomplete
import fastcomplete
import requests

from .client import get_issues


def build_parser():
    parser = argparse.ArgumentParser(prog="issuecli")
    commands = parser.add_subparsers(dest="command", required=True)
    issues = commands.add_parser("issues", help="List GitHub repository issues")
    issues.add_argument("--repo", default="psf/requests")
    issues.add_argument("--state", choices=["open", "closed", "all"], default="open")
    issues.add_argument("--limit", choices=["5", "10"], default="5")
    issues.add_argument("--format", choices=["json", "text"], default="text")
    return parser


def run(args):
    try:
        issues = get_issues(args.repo, args.state, args.limit)
    except requests.RequestException as error:
        print(f"issuecli: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(issues))
    else:
        for issue in issues:
            print(f"#{issue['number']} {issue['title']}")
    return 0


def main():
    parser = build_parser()
    fastcomplete.autocomplete(parser)
    return run(parser.parse_args())


def baseline():
    parser = build_parser()
    argcomplete.autocomplete(parser)
    return run(parser.parse_args())
