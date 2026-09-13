from io import BytesIO
import argparse
import sys
from pathlib import Path

import argcomplete
import fastcomplete
import requests
from PIL import Image

from .client import download


def build_parser():
    parser = argparse.ArgumentParser(prog="catcli", description="Download a cat from cataas.com")
    parser.add_argument("--tag", help="Cat tags, separated by commas (e.g. cute,orange)")
    parser.add_argument("--gif", action="store_true", help="Get an animated cat")
    parser.add_argument("--says", help="Text to put on the cat")
    parser.add_argument("--type", choices=["xsmall", "small", "medium", "square"])
    parser.add_argument("--filter", choices=["blur", "mono", "negate", "custom"])
    for name in ("font-size", "font-color", "brightness", "lightness", "saturation",
                 "hue", "r", "g", "b", "width", "height"):
        parser.add_argument("--" + name)
    parser.add_argument("--html", action="store_true", help="Save an HTML page")
    parser.add_argument("--json", action="store_true", help="Save JSON metadata")
    parser.add_argument("--rotate", choices=["90", "180", "270"], help="Rotate counterclockwise locally")
    parser.add_argument("--black-and-white", action="store_true", help="Convert to grayscale locally")
    parser.add_argument("--output", default="cat.jpg", help="Destination file (default: cat.jpg)")
    return parser


def run(args):
    try:
        transform = args.rotate or args.black_and_white
        if transform and (args.html or args.json):
            raise ValueError("image operations cannot be used with --html or --json")
        content = download(args)
        if transform:
            with Image.open(BytesIO(content)) as source:
                image = source.convert("L" if args.black_and_white else "RGB")
                if args.rotate:
                    image = image.rotate(int(args.rotate), expand=True)
                image.save(args.output)
        else:
            Path(args.output).write_bytes(content)
    except (requests.RequestException, OSError, ValueError) as error:
        print(f"catcli: {error}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


def main():
    parser = build_parser()
    fastcomplete.autocomplete(parser)
    return run(parser.parse_args())


def baseline():
    parser = build_parser()
    argcomplete.autocomplete(parser)
    return run(parser.parse_args())
