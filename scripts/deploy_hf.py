"""Deploy this repo to a Hugging Face Space (Docker SDK).

Reads from .env (never committed):
    HF_TOKEN       Hugging Face access token with WRITE permission
    LLM_API_KEY    stored as an encrypted Space *secret*, never uploaded as a file
    LLM_MODEL, LLM_REASONING_EFFORT, LLM_BASE_URL   stored as Space variables

Uploads every git-tracked (or new, non-ignored) file, with deploy/huggingface/{Dockerfile,README.md,start.sh}
placed at the root, because a Space needs its own README header and Dockerfile.

    python scripts/deploy_hf.py --space <hf-username>/<space-name>
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "deploy" / "huggingface"
NEVER_UPLOAD = (".env", ".venv/", "data/qdrant/", "data/checkpoints", "data/assistant", "eval/results/")


def read_env() -> dict[str, str]:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def project_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and not f.startswith(NEVER_UPLOAD) and (ROOT / f).is_file()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="<hf-username>/<space-name>")
    args = ap.parse_args()

    env = read_env()
    token = env.get("HF_TOKEN")
    if not token:
        raise SystemExit("Add HF_TOKEN=<your write token> to .env first.")
    if not env.get("LLM_API_KEY"):
        raise SystemExit("LLM_API_KEY is missing from .env.")

    api = HfApi(token=token)
    print(f"Signed in to Hugging Face as {api.whoami()['name']}")
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)

    api.add_space_secret(args.space, "LLM_API_KEY", env["LLM_API_KEY"])
    for key in ("LLM_MODEL", "LLM_REASONING_EFFORT", "LLM_BASE_URL"):
        if env.get(key):
            api.add_space_variable(args.space, key, env[key])
    api.add_space_variable(args.space, "DEMO_MODE", "true")

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for f in project_files():
            (stage / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, stage / f)
        for f in OVERRIDES.iterdir():  # Space README header, Dockerfile and start script go at the root
            shutil.copy2(f, stage / f.name)
        leaked = [p for p in stage.rglob("*") if p.is_file() and env["LLM_API_KEY"] in p.read_text(errors="ignore")]
        if leaked:
            raise SystemExit(f"Refusing to upload: the API key appears in {leaked}")
        api.upload_folder(folder_path=stage, repo_id=args.space, repo_type="space",
                          commit_message="Deploy from GitHub repo")

    print(f"Uploaded. The Space is building (first build takes ~10-20 min):\n  https://huggingface.co/spaces/{args.space}")


if __name__ == "__main__":
    main()
