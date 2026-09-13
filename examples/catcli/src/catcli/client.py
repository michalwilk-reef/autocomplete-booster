import os
from urllib.parse import quote

import requests


def download(args):
    url = os.environ.get("CATCLI_API_URL", "https://cataas.com").rstrip("/") + "/cat"
    tags = ",".join(tag for tag in (args.tag, "gif" if args.gif else None) if tag)
    if tags:
        url += "/" + quote(tags, safe=",")
    if args.says is not None:
        url += "/says/" + quote(args.says, safe="")
    params = {name: getattr(args, name) for name in (
        "type", "filter", "brightness", "lightness", "saturation", "hue",
        "r", "g", "b", "width", "height",
    )}
    if args.filter == "blur":
        params["filter"] = None
        params["blur"] = "1"
    params.update(fontSize=args.font_size, fontColor=args.font_color)
    for name in ("html", "json"):
        if getattr(args, name):
            params[name] = "true"
    headers = {"Accept": "application/json"} if args.json else {}
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.content
