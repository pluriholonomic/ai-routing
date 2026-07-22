"""Push captured data to the Hugging Face dataset repo.

Layout in the dataset repo mirrors the local staging dir:
    raw/{source}/dt=YYYY-MM-DD/{run_ts}.jsonl.gz
    curated/{table}/dt=YYYY-MM-DD/{run_ts}.parquet

The dataset repo is PRIVATE by default. Query from anywhere with DuckDB after
`CREATE SECRET (TYPE huggingface, TOKEN '<hf token>')`:
    SELECT * FROM read_parquet(
        'hf://datasets/<repo>/curated/endpoints_snapshots/*/*.parquet');
"""

import logging
import os
from pathlib import Path

from huggingface_hub import HfApi
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import DATA_DIR, HF_DATASET_REPO

log = logging.getLogger(__name__)


@retry(wait=wait_exponential(multiplier=5, min=5, max=60), stop=stop_after_attempt(5), reraise=True)
def get_api() -> HfApi:
    """HF_TOKEN env (CI) or the locally cached login (dev)."""
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    # A number of independent collectors share one HF identity.  In particular,
    # the deliberately strict whoami endpoint can transiently return 429 while
    # another workflow publishes a large capture.  Cache within the process and
    # retry the authentication check rather than dropping a scientific monitor.
    if api.whoami(cache=True) is None:  # raises if no usable token
        raise RuntimeError("no Hugging Face token available")
    return api


@retry(wait=wait_exponential(multiplier=5, min=5, max=60), stop=stop_after_attempt(5), reraise=True)
def ensure_repo(api: HfApi, repo_id: str = HF_DATASET_REPO, private: bool = True) -> None:
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)


def push(
    data_dir: Path = DATA_DIR,
    repo_id: str = HF_DATASET_REPO,
    message: str | None = None,
    delete_local: bool = False,
) -> None:
    """Upload everything under data_dir, then optionally clear it (for cron runners)."""
    api = get_api()
    ensure_repo(api, repo_id)

    # concurrent workflows (capture + scrape) can race on the parent commit
    @retry(
        wait=wait_exponential(multiplier=5, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _upload() -> None:
        api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=str(data_dir),
            commit_message=message or "orcap snapshot",
        )

    _upload()
    log.info("pushed %s to %s", data_dir, repo_id)
    if delete_local:
        for p in sorted(data_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            else:
                p.rmdir()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    push()


if __name__ == "__main__":
    main()
