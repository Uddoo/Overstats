import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:18080"
PROVINCE = "北京"
ROLE = "tank"
HERO = "猎空"
MODE = "preset"
TEST_DIR = Path(__file__).resolve().parent

CASES = [
    {
        "path": "/api/v2/dashen-rank-leaderboard",
        "payload": {"province": PROVINCE, "role": ROLE},
        "output_name": "dashen-rank-leaderboard-beijing-tank.json",
        "error_name": "dashen-rank-leaderboard-beijing-tank.error.json",
    },
    {
        "path": "/api/v2/dashen-rank-leaderboard/image",
        "payload": {"province": PROVINCE, "role": ROLE},
        "output_name": "dashen-rank-leaderboard-beijing-tank.png",
        "error_name": "dashen-rank-leaderboard-beijing-tank-image.error.json",
    },
    {
        "path": "/api/v2/dashen-hero-leaderboard",
        "payload": {"province": PROVINCE, "hero": HERO, "mode": MODE},
        "output_name": "dashen-hero-leaderboard-beijing-tracer-preset.json",
        "error_name": "dashen-hero-leaderboard-beijing-tracer-preset.error.json",
    },
    {
        "path": "/api/v2/dashen-hero-leaderboard/image",
        "payload": {"province": PROVINCE, "hero": HERO, "mode": MODE},
        "output_name": "dashen-hero-leaderboard-beijing-tracer-preset.png",
        "error_name": "dashen-hero-leaderboard-beijing-tracer-preset-image.error.json",
    },
]


for case in CASES:
    body = json.dumps(case["payload"]).encode("utf-8")
    request = Request(
        f"{BASE_URL}{case['path']}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    output_path = TEST_DIR / case["output_name"]
    error_path = TEST_DIR / case["error_name"]

    try:
        with urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())
            print(f"saved: {output_path}")
    except HTTPError as exc:
        error_body = exc.read()
        error_path.write_bytes(error_body)
        print(f"http error: {exc.code} -> {case['path']}")
        print(error_body.decode("utf-8", errors="ignore"))
        print(f"saved error body: {error_path}")
