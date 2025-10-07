# =====================================================
# hostd/qmp.py (very small QMP helper)
# =====================================================
import asyncio, json, pathlib

from common.symbols import HC_HOME
from common.logs import setup

log = setup("qmp.qemu")

import asyncio, os, stat, time

async def wait_for_qmp(path, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            if os.path.exists(path) and stat.S_ISSOCK(os.stat(path).st_mode):
                return await asyncio.open_unix_connection(path)
        except FileNotFoundError as e:
            last_err = e
        await asyncio.sleep(interval)
    raise TimeoutError(f"QMP socket not ready at {path}: {last_err}")

class QMP:
    def __init__(self, vm_id):
        sock = pathlib.Path(HC_HOME)/vm_id/"qmp.sock"
        self.sock = str(sock)

    async def _conn(self):
        log.info(f"QMP - {self.sock}")
        #reader, writer = await asyncio.open_unix_connection(self.sock)
        reader, writer = await wait_for_qmp(self.sock)
        # read greeting
        await reader.readline()
        await self.cmd(reader, writer, {"execute": "qmp_capabilities"})
        return reader, writer

    async def cmd(self, reader, writer, obj):
        writer.write((json.dumps(obj) + "\n").encode())
        await writer.drain()
        # consume one response (ignore content for scaffold)
        await reader.readline()

    async def stop(self):
        # this really means 'pause'
        r, w = await self._conn()
        await self.cmd(r, w, {"execute": "stop"}); w.close(); await w.wait_closed()

    async def cont(self):
        r, w = await self._conn()
        await self.cmd(r, w, {"execute": "cont"}); w.close(); await w.wait_closed()

    async def kill(self):
        # qemu process is killed
        r, w = await self._conn()
        await self.cmd(r, w, {"execute": "quit"}); w.close(); await w.wait_closed()

    async def powerdown(self):
        r, w = await self._conn()
        await self.cmd(r, w, {"execute": "system_powerdown"}); w.close(); await w.wait_closed()

    async def snapshot_disks(self, pairs):  # [(node_name, snap_path), ...]
        r,w = await self._conn()

        resp = await self.cmd(r, w, {"execute":"query-named-block-nodes"})
        log.info(f'snapshot_disks -- {resp}')

        # Use a QMP transaction for atomic multi-disk snapshots
        actions = [{
                    "type":"blockdev-snapshot-sync",
                    "data":{
                        "node": node,
                        "snapshot-file": snap,
                        "snapshot-node-name": "vm001_overlay_topzz-1",
                        "format":"qcow2"
                    }
                    }
                   for node, snap in pairs]
        # print({"execute":"transaction","arguments":{"actions":actions}})
        # log.debug({"execute":"transaction","arguments":{"actions":actions}})
        # r = await self.cmd(r, w, { "execute": "query-block" }); w.close(); await w.wait_closed()
        # print(json.loads(r))

        resp = await self.cmd(r, w, {"execute":"blockdev-snapshot-sync","arguments": actions[0]['data']}); log.error(f"QMP transaction resp: {resp}");  w.close(); await w.wait_closed()
        # resp = await self.cmd(r, w, {"execute":"transaction","arguments":{"actions":actions}}); log.info(f"QMP transaction resp: {resp}");  w.close(); await w.wait_closed()
        return resp

