# 🐷 Forky Pig — The Hypercomputer Playground

Forky Pig is my experiment in turning a single machine into a miniature cloud.  
It’s a system that can **spawn, snapshot, and fork virtual machines in milliseconds**, using QEMU, copy-on-write overlays, and a bit of Python orchestration magic.

It’s not production-ready, not optimized, and definitely not perfect — but it’s **real**, and it works. The point isn’t to chase scale yet; it’s to explore what “forking” compute really means when you treat VMs like living processes instead of static boxes.


[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)
[![QEMU](https://img.shields.io/badge/powered%20by-QEMU-lightgrey)](#)
[![Status](https://img.shields.io/badge/status-experimental-orange)](#)
[![Made with ❤️](https://img.shields.io/badge/made%20with-%F0%9F%92%96-lightpink)](#)

---

## 💡 What It Does

Forky Pig can:

- **Cold fork**: snapshot a paused VM and clone it instantly.  
- **Spin up isolated compute environments** using overlays, so every fork shares a base image but keeps its own writable state.  
- **Manage and orchestrate VMs** via lightweight Python daemons (`controller` and `hostd`) that talk over gRPC and QMP.  
- **Experiment with future compute ideas** — like hot forking, GPU passthrough, and distributed hypercomputing.

> “Git for VMs, with QEMU as the kernel and Python as the glue.”

---

## 🧠 Why I’m Building It

Because containers are great — until they aren’t.  
Because GPUs are scarce and orchestration is broken.  
Because I wanted to **see what would happen if you could fork a machine like a process** — instantly, cleanly, and predictably.

Forky Pig started as a joke, but it’s becoming a **serious playground** for the next generation of distributed systems — where compute is treated as something fluid, not fixed.

---

## 🏗️ Architecture
    ├── common # utilities and the like
    │   ├── ids.py
    │   ├── logs.py
    │   └── symbols.py
    ├── controller # the API interface the user talks to. it defines intent and uses hostd to do work
    │   └── server.py
    ├── guest_agent # there will be a mighty agent here someday
    ├── FP.txt # banner
    ├── hostd # the host-daemon runner, actually talks to VMs
    │   ├── qemu.py
    │   ├── qmp.py
    │   └── server.py
    ├── __init__.py
    ├── kqemu.sh # kill running processes
    ├── linux # the linux base image bits live h ere for now
    │   ├── bootbits
    │   ├── generic_alpine-3.21.4-x86_64-bios-cloudinit-metal-r0.qcow2
    │   ├── initramfs-lts
    │   ├── mnt
    │   ├── noble-server-cloudimg-amd64.img
    │   ├── root.qcow2 -> generic_alpine-3.21.4-x86_64-bios-cloudinit-metal-r0.qcow2
    │   ├── ubuntu-24.04.3-live-server-amd64.iso
    │   └── vmlinuz
    ├── proto
    │   ├── api_pb2_grpc.py
    │   ├── api_pb2.py
    │   └── api.proto
    ├── README.md
    ├── requirements.txt
    ├── run.sh # test run
    └──  scripts
        └── gen_proto.sh


Each host runs `hostd`, which controls its local QEMU instances.  
The `controller` issues fork/snapshot commands through gRPC and tracks metadata.  
Everything else is just files and processes — no Kubernetes, no magic.

---

## 🚀 Quick Start (Conceptually)

1. Create a base VM image (`.qcow2`)  
2. Launch a parent VM via the controller  
3. Call `cold_fork()`  
4. Watch it spin up children VMs sharing the same base image  

You can literally fork a live environment in seconds.  
No rebuilds, no redeploys — just a clean new world spun off from the last one.

---

## ⚙️ Current Status

| Feature | Status |
|----------|---------|
| Cold forking | ✅ Works |
| Hot forking | 🚧 Experimenting |
| Snapshot chains | 🧊 Stable |
| GPU support | 🔥 Researching |
| App-directory overlays | 🧩 Debating |
| Multi-host orchestration | 💭 Planned |

---

## 🧰 Built With

- Python 3 (asyncio, gRPC)  
- QEMU / QMP  
- qcow2 overlays  
- Linux KSM (for deduplication)  
- Bash & a bit of insanity  

---

## 🤠 Philosophy

Forky Pig isn’t about reinventing the wheel —  
it’s about spinning up **thousands of wheels instantly**  
and seeing what they can build together.

---

## 📜 License

This work is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License.
To view a copy of this license, visit http://creativecommons.org/licenses/by-nc/4.0/


## Setup configs misc

Some of theses were required to get the system running. KSM is the paging de-duplication

    apt install qemu-system-x86
    
    grep KSM /boot/config-$(uname -r)
    CONFIG_KSM=y # we want this
    
    sudo modprobe ksm
    
    echo 1 | sudo tee /sys/kernel/mm/ksm/run


Use this to actually run the code for now. See the `run.sh` for how a client could look

    unset PYTHONPATH
    . .venv/bin/activate
    export PYTHONPATH=.
    
    python3 {hostd,controller}/server.py
