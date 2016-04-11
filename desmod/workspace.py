import os
import shutil


class Workspace(object):
    def __init__(self, workspace, overwrite=False):
        self.workspace = workspace
        self.overwrite = overwrite
        self.prev_dir = None

    def __enter__(self):
        if self.overwrite and os.path.isdir(self.workspace):
            shutil.rmtree(self.workspace)
        os.makedirs(self.workspace)
        self.prev_dir = os.getcwd()
        os.chdir(self.workspace)

    def __exit__(self, *exc):
        os.chdir(self.prev_dir)
