"""Optional private HF dataset mirror for a small, single-instance shared demo."""
import os
from pathlib import Path
from threading import RLock
LOCK=RLock()
REPO=os.environ.get('HF_STATE_REPO','')

def restore(store):
    if os.environ.get('SPACE_ID') and not REPO:
        raise RuntimeError('Set HF_STATE_REPO and HF_TOKEN before starting: Space disks are temporary.')
    if REPO:
        from huggingface_hub import snapshot_download
        snapshot_download(REPO,repo_type='dataset',local_dir=str(store),ignore_patterns=['README.md','.gitattributes'])

def persist(store,paths):
    if not REPO:return
    from huggingface_hub import HfApi,CommitOperationAdd
    with LOCK:
        files=[]
        for path in paths:
            path=Path(path)
            files.extend([path] if path.is_file() else [p for p in path.rglob('*') if p.is_file()])
        HfApi().create_commit(repo_id=REPO,repo_type='dataset',commit_message='Save studio artifacts',operations=[CommitOperationAdd(path_in_repo=str(p.relative_to(store)),path_or_fileobj=str(p)) for p in files])
