import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


base_url = "http://127.0.0.1:18080"
bnet_id = "oL1ama#5684"
text = f"帮我看一下 {bnet_id} 这周总结"
test_dir = Path(__file__).resolve().parent
output_path = test_dir / "auto-route-summary-week.json"

body = json.dumps({"text": text}).encode("utf-8")
request = Request(
    f"{base_url}/api/v2/auto-route",
    data=body,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)

try:
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        output_path.write_bytes(payload)
        print(f"saved: {output_path}")
except HTTPError as exc:
    error_body = exc.read()
    output_path.write_bytes(error_body)
    print(f"http error: {exc.code}")
    print(error_body.decode('utf-8', errors='ignore'))
    print(f"saved error body: {output_path}")
