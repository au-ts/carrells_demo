#!/usr/bin/env sh

# Check if target machine is provided
if [ -z "$1" ]; then
    echo "Error: Target machine not provided."
    echo "Usage: $0 <target_machine_name>"
    exit 1
fi

target_machine="$1"

rm -rf build && \
make all -j$(nproc) BUILD_DIR=build MICROKIT_BOARD=x86_64_generic_vtx X86_BOARD=${target_machine} MICROKIT_CONFIG=smp-debug MICROKIT_SDK=/Users/terrybai/ts/microkit/release/microkit-sdk-2.3.0-dev
/Users/terrybai/tmp/machine_queue/mq.sh run -s ${target_machine} -f ./build/sel4.elf -f ./build/loader.img -c "fnjkeqhtreqfgkjadfg"
