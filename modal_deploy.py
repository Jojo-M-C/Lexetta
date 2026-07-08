"""
Deploy the LCP Modal app with the model config from .env.

Reads LCP_MODEL_DIR / LCP_MODEL_TOKEN / LCP_MODEL_REVISION from .env, pushes
them to the `lcp-model` Modal secret (overwriting it if it exists), then runs
`modal deploy app/lib/lcp_modal.py`.

Usage (from the repo root, inside the project venv):
    python modal_deploy.py
"""

import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent
SECRET_NAME = "lcp-model"
MODAL_APP_FILE = REPO_ROOT / "app" / "lib" / "lcp_modal.py"


def main() -> None:
    env = dotenv_values(REPO_ROOT / ".env")

    model_dir = env.get("LCP_MODEL_DIR")
    if not model_dir:
        sys.exit("LCP_MODEL_DIR is missing from .env — set it to the HF repo id of the model.")

    secret_values = {
        "LCP_MODEL_DIR": model_dir,
        "LCP_MODEL_TOKEN": env.get("LCP_MODEL_TOKEN") or "",
        "LCP_MODEL_REVISION": env.get("LCP_MODEL_REVISION") or "",
    }

    print(f"Updating Modal secret '{SECRET_NAME}' (LCP_MODEL_DIR={model_dir})")
    # --force overwrites the secret if it already exists, so this script can be
    # re-run after every .env change. sys.executable keeps us in the same venv.
    subprocess.run(
        [sys.executable, "-m", "modal", "secret", "create", "--force", SECRET_NAME]
        + [f"{key}={value}" for key, value in secret_values.items()],
        check=True,
    )

    print(f"Deploying {MODAL_APP_FILE.relative_to(REPO_ROOT)}")
    subprocess.run(
        [sys.executable, "-m", "modal", "deploy", str(MODAL_APP_FILE)],
        check=True,
        cwd=REPO_ROOT,
    )


if __name__ == "__main__":
    main()
