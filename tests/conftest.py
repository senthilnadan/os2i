import os

os.environ.setdefault("TRANSITION2EXEC_BACKEND", "stub")

from transition2exec.config import settings

settings.backend = os.environ["TRANSITION2EXEC_BACKEND"]
