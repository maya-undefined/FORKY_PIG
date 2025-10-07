# =====================================================
# controller/server.py (grpc.aio)
# =====================================================
import asyncio
from typing import Dict, List, Deque, Optional
import grpc

from dataclasses import dataclass, field
from collections import deque

from proto import api_pb2 as pb
from proto import api_pb2_grpc as rpc

from common.logs import setup
from common.ids import new_id

log = setup("controller")

class HostInfo:
    def __init__(self, addr: str, inv: pb.InventoryResp, client: 'rpc.HostdAPIStub'):
        self.addr = addr
        self.inv = inv
        self.client = client

class VM:
    def __init__(self, vm_id: str, host: str, shape: pb.Shape, gpu_bdf: str, ip: str = "", pool: str = ""):
        self.id = vm_id
        self.host = host
        self.shape = shape
        self.gpu_bdf = gpu_bdf
        self.ip = ip
        self.state = "PAUSED_WARM"
        self.pool = pool

@dataclass
class PoolState:
    id: str
    name: str
    tenant_id: str
    guests: List[str] = field(default_factory=list) # host names (inv.host)
    warm: Dict[str, Deque[str]] = field(default_factory=dict) # shape_key -> deque of vm_ids
    lock: asyncio.Lock = field(default_factory=asyncio.Lock) # per-pool lock

class Controller(rpc.ControllerAPIServicer):
    def __init__(self):
        self.hosts: Dict[str, HostInfo] = {}
        self.vms: Dict[str, VM] = {}
        self.warm: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()
        self.pools: Dict[str, PoolState] = {}

    @staticmethod
    def shape_key(s: pb.Shape) -> str:
        return f"{s.vcpu}c-{s.ram_gb}g-{s.gpu_model}"

    def _get_pool(self, pool_id: str, context) -> PoolState:
        p = self.pools.get(pool_id)
        if not p:
            raise grpc.RpcError(grpc.StatusCode.NOT_FOUND, "unknown pool")

        return p

    async def CreatePool(self, request: pb.CreatePoolReq, context) -> pb.CreatePoolResp:
        pool_id = new_id()
        spec = request.spec
        p = PoolState(id=pool_id, name=spec.name or pool_id, tenant_id=spec.tenant_id or "default")
        self.pools[pool_id] = p
        return pb.CreatePoolResp(pool=pb.Pool(id=p.id, name=p.name, tenant_id=p.tenant_id, hosts=list(p.guests)))

    async def ListPools(self, request: pb.Empty, context) -> pb.ListPoolsResp:
        items = [pb.Pool(id=p.id, name=p.name, tenant_id=p.tenant_id, hosts=list(p.guests)) for p in self.pools.values()]
        return pb.ListPoolsResp(pools=items)

    async def ListPoolHosts(self, req: pb.ListPoolsHostsReq, context) -> pb.ListPoolsHostsResp:
        pool_id = req.pool_id
        pool = self._get_pool(pool_id, context)
        items = pool.guests
        return pb.ListPoolsHostsResp(hosts=items)

    async def EnsureWarmPool(self, request: pb.EnsureWarmPoolReq, context) -> pb.EnsureWarmPoolResp:
        pool = self._get_pool(request.pool_id, context)
        key = self.shape_key(request.shape)
        async with pool.lock:
            cur = len(pool.warm.get(key, deque()))

        need = request.target - cur
        # if need <= 0:
        #     return pb.EnsureWarmPoolResp(current=cur)

        # naive spread: first host only (MVP)
        for host_name, h in self.hosts.items():
            for i in range(need):
                bdf = h.inv.gpus_bdf[i % max(1, len(h.inv.gpus_bdf))] if h.inv.gpus_bdf else "0000:00:00.0"
                try:
                    resp = await h.client.SpawnWarm(pb.HostSpawnWarmReq(shape=request.shape, gpu_bdf=bdf))
                except Exception as e:
                    log.error(f"EnsureWarmPool -- SpawnWarm on {host_name} failed: {e}")
                    continue
                vm = VM(resp.vm_id, host=h.inv.host, shape=request.shape, gpu_bdf=bdf, pool=pool.id)
                log.info(f"VM Info: {resp.vm_id}")
                async with pool.lock:
                    self.vms[vm.id] = vm
                    pool.warm.setdefault(key, deque()).append(vm.id)
                cur += 1
                pool.guests.append(vm.id)
                if cur >= request.target:
                    return pb.EnsureWarmPoolResp(current=cur)
        return pb.EnsureWarmPoolResp(current=cur)

    async def Fork(self, request: pb.EnsureWarmPoolReq, context) -> pb.EnsureWarmPoolResp:
        vm_id = request.vm_id
        vm = self.vms[vm_id]
        h = self.hosts[vm.host]

        pool_id = vm.pool

        pool = self._get_pool(pool_id, context)
        key = self.shape_key(vm.shape)
        async with pool.lock:
            cur = len(pool.warm.get(key, deque()))
        # TODO: Someday we will want to fork into another pool. That could be easy to do here. 

        need = request.how_many #- cur
        # if need <= 0:
        #     return pb.EnsureWarmPoolResp(current=cur)

        r = await h.client.GetOverlays(pb.OverlayReq(vm_id=request.vm_id))
        # overlays = {}
        overlays = dict(r.overlays)

        log.info(f'Fork -- overlays={type(dict(overlays))} overlays={dict(overlays)}')
        # 1. get overlays from source vm call here
        #   - on hostd: pause vm, get overlays, unpause vm
        # 2. give overlay to SpawnWarm
        #   - on hostd: get overlays, feed overlays into start_qemu()
        # 3. Return lists

        # naive spread: first host only (MVP)
        # for host_name, h in self.hosts.items():
            # eventually this will have to 'find' empty-enough hostd capacity, and get those rather than 
            # iterate through the list of hosts
            # the below 

        host_name = [self.hosts.keys()][0]
        child_vms = list()
        for i in range(need):
            bdf = h.inv.gpus_bdf[i % max(1, len(h.inv.gpus_bdf))] if h.inv.gpus_bdf else "0000:00:00.0"
            # log.info(f'fork -- {vm.shape}')
            try:
                resp = await h.client.SpawnWarm(pb.HostSpawnWarmReq(shape=vm.shape, snapshot=overlays, gpu_bdf=bdf))
            except Exception as e:
                log.error(f"Fork -- SpawnWarm on {host_name} failed: {e}")
                continue
            vm = VM(resp.vm_id, host=h.inv.host, shape=vm.shape, gpu_bdf=bdf)
            log.info(f"VM Info: {resp.vm_id}")
            async with pool.lock:
                self.vms[vm.id] = vm
                pool.warm.setdefault(key, deque()).append(vm.id)
            cur += 1
            pool.guests.append(vm.id)
            child_vms.append(vm.id)
            # if cur >= request.target:
            #     return pb.ForkResp(vm_ids=child_vms)
        return pb.ForkResp(vm_ids=child_vms)

    async def Acquire(self, request: pb.AcquireReq, context) -> pb.AcquireResp:
        #TODO Need to adapt Pools for this method
        key = self.shape_key(request.shape)
        async with self._lock:
            ids = self.warm.get(key, [])
            if not ids:
                context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "no warm VMs; add fallback later")
            vm_id = ids.pop(0)
            vm = self.vms[vm_id]
        h = self.hosts[vm.host]
        await h.client.Unpause(pb.VMId(vm_id=vm.id))
        vm.state = "RUNNING"
        handle = pb.VMHandle(vm_id=vm.id, host=vm.host, ip=vm.ip, ssh_key_ref="devbox-default")
        return pb.AcquireResp(vm=handle)

    async def Release(self, request: pb.ReleaseReq, context) -> pb.Empty:
        #TODO Need to adapt Pools for this method
        vm = self.vms.get(request.vm_id)
        if not vm:
            return pb.Empty()
        h = self.hosts[vm.host]
        if request.recycle:
            await h.client.Pause(pb.VMId(vm_id=vm.id))
            vm.state = "PAUSED_WARM"
            key = self.shape_key(vm.shape)
            async with self._lock:
                self.warm.setdefault(key, []).append(vm.id)
        else:
            await h.client.Destroy(pb.VMId(vm_id=vm.id))
            vm.state = "DESTROYED"
        return pb.Empty()

    async def Exec(self, request: pb.ExecReq, context) -> pb.ExecResp:
        vm = self.vms.get(request.vm_id)
        if not vm:
            context.abort(grpc.StatusCode.NOT_FOUND, "unknown vm")
        h = self.hosts[vm.host]
        return await h.client.Exec(pb.HostExecReq(vm_id=vm.id, argv=request.argv, timeout_sec=request.timeout_sec))

    async def Health(self, request: pb.Empty, context) -> pb.HealthResp:
        return pb.HealthResp(status="ok")

async def serve():
    server = grpc.aio.server()
    ctrl = Controller()

    # Seed one hostd (localhost:50052) for the scaffold
    ch = grpc.aio.insecure_channel("127.0.0.1:50052")
    hostcli = rpc.HostdAPIStub(ch)
    inv = await hostcli.ReportInventory(pb.Empty())
    ctrl.hosts[inv.host] = HostInfo(addr="127.0.0.1:50052", inv=inv, client=hostcli)

    rpc.add_ControllerAPIServicer_to_server(ctrl, server)
    server.add_insecure_port("[::]:50051")
    log.info("controller listening :50051")
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())