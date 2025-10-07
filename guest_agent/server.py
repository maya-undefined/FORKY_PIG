
# =====================================================
# guest_agent/server.py (grpc.aio)
# =====================================================
import asyncio, shutil
import grpc
from proto import api_pb2 as pb
from proto import api_pb2_grpc as rpc
from common.logs import setup

log = setup("guest-agent")

class Agent(rpc.AgentAPIServicer):
    async def SelfTestGpu(self, request: pb.Empty, context) -> pb.HealthResp:
        if shutil.which("nvidia-smi") is None:
            return pb.HealthResp(status="gpu-missing")
        proc = await asyncio.create_subprocess_exec("nvidia-smi", "-L", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.wait()
        return pb.HealthResp(status="gpu-ok" if proc.returncode == 0 else "gpu-fail")

    async def Exec(self, request: pb.HostExecReq, context) -> pb.ExecResp:
        proc = await asyncio.create_subprocess_exec(*request.argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=max(1, request.timeout_sec))
        except asyncio.TimeoutError:
            proc.kill(); return pb.ExecResp(exit_code=124, stdout=b"", stderr=b"timeout")
        return pb.ExecResp(exit_code=proc.returncode, stdout=out, stderr=err)

    async def TeardownCleanup(self, request: pb.Empty, context) -> pb.Empty:
        # TODO: clean /tmp, kill known processes, etc.
        return pb.Empty()

async def serve():
    server = grpc.aio.server()
    rpc.add_AgentAPIServicer_to_server(Agent(), server)
    server.add_insecure_port("[::]:50053")
    log.info("guest-agent listening :50053")
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())