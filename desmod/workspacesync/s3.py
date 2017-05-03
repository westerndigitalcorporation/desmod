"""Synchronization of workspace artifacts to Amazon S3 cloud storage."""
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
        self.client = None
        self.config = config
        self.workspace = config['sim.workspace']
        self.artifacts = artifacts

    def _upload_artifact(self, artifact):
        dest = os.path.join(
            self.config['sim.sync.s3.prefix'],
            os.path.split(self.workspace)[1],
            (artifact[2:]))
        self.client.upload_file(
            artifact, self.config['sim.sync.s3.bucket'], dest)

    def sync(self):
        """Concurrently upload the artifacts to s3."""
        from concurrent.futures import ThreadPoolExecutor
        import boto3

        self.config.setdefault('sim.sync.s3.prefix', '')
        self.client = boto3.client('s3')

        if len(self.artifacts) == 0:
            return

        futures = []
        with ThreadPoolExecutor(max_workers=self.MAX_THREADS) as executor:
            for artifact in self.artifacts:
                futures.append(
                    executor.submit(self._upload_artifact, artifact))
        [future.result() for future in futures]
