from src.config.config import Config
from src.storage.redis_connection import RedisConnection
import os
import src.logger.log as log

from src.common.utils import (
    find_uses_strings,
)

from src.downloader.download import (
    download_action_or_reusable_workflow,
)

from src.downloader.utils import (
    insert_workflow_or_action_to_redis,
    add_ref_pointer_to_redis,
)


def get_local_repository_workflows(path: str) -> dict:
    workflows = {}
    path = os.path.join(path, '.github/workflows')

    for filename in os.listdir(path):
        if any(filename.endswith(extension) for extension in ['.yml', '.yaml']):
            workflows[filename] = os.path.join(path, filename)
    return workflows


def local_workflows_and_actions(path: str, only_workflows: list = []) -> None:
    with RedisConnection(Config.redis_objects_ops_db) as ops_db:
        workflows = get_local_repository_workflows(path)
        is_public = 0   # Always treat as private.

        log.debug(f"[+] Found {len(workflows)} workflows in {path}")
        for name, local_path in workflows.items():
            if len(only_workflows) > 0 and name.lower() not in only_workflows:
                log.debug(f"[+] Skipping {name}")
                continue

            log.debug(f"[+] Reading {name}")
            with open(local_path, 'r') as f:
                contents = f.read()

            uses_strings = find_uses_strings(contents)
            for uses_string in uses_strings:
                download_action_or_reusable_workflow(uses_string=uses_string, repo=path)

            workflow_unix_path = os.path.join(path, '.github/workflows', name)
            github_url = workflow_unix_path
            insert_workflow_or_action_to_redis(
                db=Config.redis_workflows_db,
                object_path=workflow_unix_path,
                data=contents,
                github_url=github_url,
                is_public=is_public,
            )

            # In the future, ref will be with commit sha
            add_ref_pointer_to_redis(workflow_unix_path, workflow_unix_path)

        ops_db.insert_to_set(Config.workflow_download_history_set, path)


def download_local_repo_workflows_and_actions():
    """Scan local repository
    Identical functionality to downloading a single repo, but we're looking
    for the initial workflows locally. We still need the GITHUB_TOKEN, as
    any 'uses' actions and workflows will still be downloaded from GitHub.
    """
    log.info(f"[+] Scanning local repository")

    only_workflows = []
    if Config.workflow is not None and len(Config.workflow) > 0:
        only_workflows = list(map(str.lower, Config.workflow))
        log.info(f"[+] Will only scan the following workflows: {', '.join(only_workflows)}")

    for path in Config.path:
        if not os.path.isdir(path):
            log.error(f"[-] Local repository '{path}' does not exist")
            log.fail_exit()

        local_workflows_and_actions(path, only_workflows=only_workflows)
