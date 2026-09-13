import os

import requests


def get_issues(repository, state, limit):
    base_url = os.environ.get("ISSUECLI_API_URL", "https://api.github.com")
    response = requests.get(
        f"{base_url}/repos/{repository}/issues",
        params={"state": state, "per_page": limit},
        headers={"Accept": "application/vnd.github+json"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
