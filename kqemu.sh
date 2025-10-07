#!/usr/bin/env sh

for i in `ps aux | grep qemu-system-x86_64 | awk '{print $2}' `; do kill $i; done
