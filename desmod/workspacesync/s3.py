from concurrent.futures import ThreadPoolExecutor

import boto3
import getpass
import os


class S3Sync(object):
    """S3 workspace synchronization.

    The :class:`S3Sync` class implements a sync method that synchronizes the
    workspace artifacts to an S3 bucket with a configured key prefix.  The
    s3 destination is of the format: /{prefix}/{workspace name}/{artifact path}

    :param dict config: A fully-initialized configuration dictionary.
    :param list artifacts: A list of artifact paths relative to the workspace
        directory. E.g., ["./0/results.yaml"].

    """

    MAX_THREADS = 10

    def __init__(self, config, artifacts):
        self.client = boto3.client('s3')
        self.config = config
        self.workspace = config['sim.workspace']
        self.artifacts = artifacts

    def _upload_artifact(self, artifact):
        dest = os.path.join(
                self.config['sim.workspace.s3_sync_prefix'],
                os.path.split(self.workspace)[1],
                (artifact[2:]))
        self.client.upload_file(
                artifact, self.config['sim.workspace.s3_sync_bucket'], dest)

    def sync(self):
        """Concurrently upload the artifacts to s3."""
        self.init_config_vals(self.config)
        if len(self.artifacts) == 0:
            return

        futures = []
        with ThreadPoolExecutor(max_workers=self.MAX_THREADS) as executor:
            for artifact in self.artifacts:
                futures.append(
                        executor.submit(self._upload_artifact, artifact))
        [future.result() for future in futures]


    @staticmethod
    def init_config_vals(config):
        """Set sane s3 config values if they have not yet been set."""
        if not config['sim.workspace.s3_sync_prefix']:
            try:
                username = getpass.getuser()
            except:
                username = "unknown"
            config['sim.workspace.s3_sync_prefix'] = username
