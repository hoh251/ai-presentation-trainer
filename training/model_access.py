"""Check local Hugging Face access without printing or persisting the token."""
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL_FILE = "https://huggingface.co/google/embeddinggemma-300m/resolve/main/model.safetensors"


def get_token() -> str | None:
    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        return token
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "HF_TOKEN":
                return value.strip().strip('"\'') or None
    return None


def check_access() -> bool:
    token = get_token()
    if not token:
        print("HF_TOKEN is not configured. Set the environment variable or training/.env.")
        return False
    request = Request(MODEL_FILE, headers={"Authorization": f"Bearer {token}"}, method="HEAD")
    try:
        with urlopen(request, timeout=20) as response:
            print(f"Model file access: HTTP {response.status}")
            return response.status == 200
    except HTTPError as error:
        print(f"Model file access: HTTP {error.code}. Check that your Hugging Face account accepted the model terms.")
    except URLError:
        print("Model file access: network connection failed.")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if check_access() else 1)
