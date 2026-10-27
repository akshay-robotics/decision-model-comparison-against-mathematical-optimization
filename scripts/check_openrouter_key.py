"""Read-only OpenRouter key check; never prints the key itself."""

from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trafficlab.openrouter import load_api_key
from trafficlab.security import open_api_request as urlopen


def main() -> int:
    key = load_api_key()
    if not key:
        print("No OpenRouter key found. Set OPENROUTER_API_KEY or add it to the project .env file.")
        return 2
    request = Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                print(f"OpenRouter key check returned HTTP {response.status}.")
                return 1
    except HTTPError as exc:
        print(f"OpenRouter rejected the key (HTTP {exc.code}).")
        return 1
    except (URLError, TimeoutError) as exc:
        print(f"Could not reach OpenRouter: {exc.reason if isinstance(exc, URLError) else exc}.")
        return 1
    print("OpenRouter accepted the key. No model call was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
