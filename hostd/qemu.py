# =====================================================
# hostd/qemu.py (spawn/pause/unpause stubs)
# =====================================================
import asyncio, os, pathlib, shlex, time
from subprocess import CalledProcessError

from common.logs import setup
from common.symbols import HC_HOME

log = setup("hostd.qemu")

BASE_DIR = pathlib.Path(HC_HOME)
BASE_DIR.mkdir(parents=True, exist_ok=True)

async def start_qemu(vmid: str, gpu_bdf: str, overlays: dict = {}, from_fork: bool = False) -> None:
    """Start QEMU with a VFIO GPU? someday attached. Minimal flags for MVP scaffold."""
    vdir = BASE_DIR / vmid
    vdir.mkdir(parents=True, exist_ok=True)
    qmp_sock = vdir / "qmp.sock"

    parent_overlay = overlays.get('overlay', None)
    vmstate_overlay = overlays.get('vmstate', None)

    if parent_overlay:
        # overlay_cmd = (
        #     "cp " 
        #     # "--reflink=always " # this is supported for btrfs -- instant copy; ext4 copies everything (and errors)
                                    # the original file DOESN"T get over written in btrfs, it gets a new inode to replace it
                                    # i.e., btrfs, zfs, etc are copy-on write, too!
        #     "{parent_overlay} " 
        #     "{vdir}/vm-001.overlay.qcow2 "
        # ).format(vdir=str(vdir), parent_overlay=parent_overlay)
        overlay_cmd = (
            "qemu-img create -f qcow2 -F qcow2 "
            "-b {parent_overlay} "
            "{vdir}/vm-001.overlay.qcow2 "
        ).format(vdir=str(vdir), parent_overlay=parent_overlay)
    else:
        overlay_cmd = (
            "qemu-img create -f qcow2 -F qcow2 "
            "-b ../../linux/root.qcow2 "
            "{vdir}/vm-001.overlay.qcow2 "
        ).format(vdir=str(vdir))

    log.info(f'qemu overlay creation: overlay_cmd={overlay_cmd} parent_overlay={parent_overlay} overlays={overlays}')

    wait_flag = 'on'
    # this causes the qemu process to wait before the sock is ready


    base_image_chain = (
        # overlay (writable)            
        "-blockdev driver=file,filename={vdir}/vm-001.overlay.qcow2,locking=on,node-name=ovlfile "
        "-blockdev driver=qcow2,file=ovlfile,node-name=overlay "
    ).format(vdir=vdir)

    cmd = (
        # create overlay for this particular VM
        "{overlay_cmd} "
        
        " ; " # this allows to run 2 cmds concurrently
        
        "qemu-system-x86_64 "
        # prevent the qemu process from grabbing the server's TTY 
        "-display none -serial none -monitor none -parallel none -daemonize "

        # keep track of logs, pid files
        "-pidfile {vdir}/qemu.pid "
        "-D {vdir}/qemu.log -msg timestamp=on "

        # use lean q35 pcie for VFIO, turn off unused systems
        "-machine q35,accel=kvm,kernel-irqchip=on,usb=off,vmport=off,smm=off,mem-merge=on "
        "-cpu host,+invtsc,-hypervisor "
        "-smp 2 -m 1048 " # TODO: make this configurable
        
        # turn this on when we can run as root
        #"-mem-path /dev/hugepages -mem-prealloc "
        "-nodefaults -no-user-config "
        "-rtc base=utc,clock=host "
        "-overcommit mem-lock=on "
        "-object iothread,id=ioth0 "
        
        # uhh....network forthcoming
        #"-netdev tap,id=net0,script=/etc/qemu-ifup,downscript=/etc/qemu-ifdown,vhost=on,queues=4 "
        #"-device virtio-net-pci,netdev=net0,mq=on,vectors=10 "
        # These two lines below will make us be able to ssh into this, the host,port will have to be unique
        # "-netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22 "
        # "-device virtio-net-pci,netdev=net0 "

        # # base (opened read-only)
        # "-blockdev driver=file,filename=./linux/root.qcow2,locking=on,node-name=basefile "
        # "-blockdev driver=qcow2,file=basefile,read-only=on,node-name=basenode "

        # # overlay (writable)
        # "-blockdev driver=file,filename={vdir}/vm-001.overlay.qcow2,locking=on,node-name=ovlfile "
        # "-blockdev driver=qcow2,file=ovlfile,backing=basenode,node-name=overlay "
        # #"-blockdev driver=raw,node-name=vmroot,file.driver=file,file.filename=./linux/root.qcow2,cache.direct=on,cache.no-flush=on "
        "{base_image_chain} "

        # attach the device
        "-device virtio-blk-pci,drive=overlay,iothread=ioth0,bootindex=1 "

        "-kernel ./linux/vmlinuz "
        "-append \"root=/dev/vda rw console=ttyS0 tsc=reliable mitigations=off\" "
        "-device pcie-root-port,id=rp0,chassis=1,slot=1 "
        "-device pcie-root-port,id=rp1,chassis=2,slot=2 "

        # forthcoming GPU suppport
        #"-device vfio-pci,host=0000:41:00.0,bus=rp0 "
        #"-device vfio-pci,host=0000:41:00.1,bus=rp1 "

        "-qmp unix:{qmp},server=on,wait={wait_flag} "
    ).format(
        qmp=str(qmp_sock), bdf=gpu_bdf, vdir=vdir, 
        base_dir=BASE_DIR, wait_flag=wait_flag, 
        overlay_cmd=overlay_cmd, base_image_chain=base_image_chain
    )

    log.info("QEMU start: %s", cmd)
    proc = await asyncio.create_subprocess_shell(cmd)
    #rc = await proc.wait()
    #if rc != 0:
    #    raise CalledProcessError(rc, cmd)

async def destroy_qemu(vmid: str) -> None:
    # Scaffold: a real impl would track pids; here we rely on teardown elsewhere
    vdir = BASE_DIR / vmid
    cmd = (
        #"kill -9 `cat {vdir}/qemu.pid` "
        #" ; "
        "rm -rf {vdir}"
    ).format(vdir=vdir)
    log.info(f"QEMU KILL: {cmd}")
    proc = await asyncio.create_subprocess_shell(cmd)
