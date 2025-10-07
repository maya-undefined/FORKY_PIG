# =====================================================
# hostd/server.py (grpc.aio)
# =====================================================
import asyncio
import pathlib
from typing import Dict
import grpc

from proto import api_pb2 as pb
from proto import api_pb2_grpc as rpc

from common.logs import setup
from common.ids import new_id
from qemu import start_qemu, destroy_qemu
from qmp import QMP

log = setup("hostd")

from common.symbols import HC_HOME

class VMRec:
    def __init__(self, vm_id: str, gpu_bdf: str, ip: str = ""):
        self.id = vm_id
        self.gpu_bdf = gpu_bdf
        self.ip = ip
        self.state = "PAUSED_WARM"

class Hostd(rpc.HostdAPIServicer):
    def __init__(self, host_name: str = "host-01"):
        self.host = host_name
        self.vms: Dict[str, VMRec] = {}
        self.gpus = ["0000:65:00.0"]  # scaffold

    async def ReportInventory(self, request: pb.Empty, context) -> pb.InventoryResp:
        return pb.InventoryResp(host=self.host, cpus=64, mem_bytes=512<<30, gpus_bdf=self.gpus)

    async def BindGpuToVfio(self, request: pb.GpuBDF, context) -> pb.Empty:
        log.info("bind %s to vfio-pci (scaffold)", request.bdf)
        return pb.Empty()

    async def GpuReset(self, request: pb.GpuBDF, context) -> pb.Empty:
        log.info("FLR reset %s (scaffold)", request.bdf)
        return pb.Empty()

    async def SpawnWarm(self, request: pb.HostSpawnWarmReq, context) -> pb.HostSpawnWarmResp:
        o = getattr(request, 'snapshot', None)
        log.info(f'SpawnWarm called -- {o}')
        vmid = new_id()
        await start_qemu(vmid, request.gpu_bdf, overlays=o)

        # if you try this now, there is a race condition; the qmp.sock file hasn't been created yet!
        # qmp = QMP(vmid); qmp.cont()

        self.vms[vmid] = VMRec(vmid, request.gpu_bdf)
        return pb.HostSpawnWarmResp(vm_id=vmid)

    async def AcquireWarm(self, request: pb.HostAcquireWarmReq, context) -> pb.HostAcquireWarmResp:
        for vid, v in self.vms.items():
            if v.state == "PAUSED_WARM":
                return pb.HostAcquireWarmResp(vm_id=vid)
        context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "no warm VMs")

    async def FastRestore(self, request: pb.HostFastRestoreReq, context) -> pb.HostFastRestoreResp:
        vmid = new_id()
        await start_qemu(vmid, request.gpu_bdf)
        qmp = QMP(vmid)
        await qmp.cont()
        self.vms[vmid] = VMRec(vmid, request.gpu_bdf)
        return pb.HostFastRestoreResp(vm_id=vmid)

    async def Unpause(self, request: pb.VMId, context) -> pb.Empty:
        qmp = QMP(request.vm_id)
        await qmp.cont()
        self.vms[request.vm_id].state = "RUNNING"
        return pb.Empty()

    async def Pause(self, request: pb.VMId, context) -> pb.Empty:
        qmp = QMP(request.vm_id)
        await qmp.stop()
        self.vms[request.vm_id].state = "PAUSED_WARM"
        return pb.Empty()

    async def Destroy(self, request: pb.VMId, context) -> pb.Empty:
        # Scaffold: would signal QEMU to quit and delete overlay
        self.vms.pop(request.vm_id, None)
        qmp = QMP(request.vm_id)
        await qmp.kill()
        await destroy_qemu(request.vm_id)
        return pb.Empty()

    async def Exec(self, request: pb.HostExecReq, context) -> pb.ExecResp:
        # Scaffold: would call guest-agent inside the VM; placeholder runs locally
        proc = await asyncio.create_subprocess_exec(*request.argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=max(1, request.timeout_sec))
        except asyncio.TimeoutError:
            proc.kill(); return pb.ExecResp(exit_code=124, stdout=b"", stderr=b"timeout")
        return pb.ExecResp(exit_code=proc.returncode, stdout=stdout, stderr=stderr)

    async def GetOverlays(self, request: pb.OverlayReq, context) -> pb.OverlayResp:
        vm_id = request.vm_id
        device_path = pathlib.Path(HC_HOME)/vm_id 
        device = [('overlay', f'{str(device_path.resolve())}/vm-001.overlay-top.qcow2')]

        qmp = QMP(request.vm_id)
        await qmp.stop()
        # Step 1: Put the VM to sleep

        # res = await qmp.snapshot_disks(pairs=device)
        # this isn't working for right now

        source_path = "vm-001.overlay.qcow2"
        vdir = pathlib.Path(HC_HOME)/vm_id #source_path
        parent_overlay = device[0][1]
        overlay_cmd = (
            "qemu-img create -f qcow2 -F qcow2 "
            "-b {vdir}/vm-001.overlay.qcow2 "
            "{parent_overlay} "
        ).format(vdir=str(vdir.resolve()), parent_overlay=parent_overlay)
        log.info(f'GetOverlays -- {request.vm_id} cmd={overlay_cmd}')
        # Step 2: Get a VM image snapshot

        import time, os
        interval = 0.01
        deadline = time.time() + 5.0 # 5 seconds may be too much
        last_err = None
        path = f"{HC_HOME}/{vm_id}/vm-001.overlay.qcow2"
        while time.time() < deadline:
            try:
                if os.path.exists(path):
                    proc = await asyncio.create_subprocess_shell(overlay_cmd)
                    stdout, stderr = await proc.communicate() # actually do step #2
                    break
            except FileNotFoundError as e:
                last_err = e
            await asyncio.sleep(interval)

        await qmp.cont()
        # Step 3: re-awaken the parent VM

        return pb.OverlayResp(overlays={device[0][0]: device[0][1]})

async def serve():
    server = grpc.aio.server()
    rpc.add_HostdAPIServicer_to_server(Hostd(), server)
    server.add_insecure_port("[::]:50052")
    log.info("hostd listening :50052")
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())
