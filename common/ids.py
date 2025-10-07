# =====================================================
# common/ids.py
# =====================================================
import os, binascii

def new_id(nbytes: int = 6) -> str:
    return binascii.hexlify(os.urandom(nbytes)).decode()
