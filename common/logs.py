# =====================================================
# common/logs.py
# =====================================================
import logging, sys

def setup(name: str = "devbox", level: int = logging.INFO):
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        h.setFormatter(fmt)
        log.addHandler(h)
        log.propagate = False # prevents duplicate log entries being printed
    log.setLevel(level)
    return log
