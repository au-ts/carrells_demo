# Copyright 2026, UNSW
# SPDX-License-Identifier: BSD-2-Clause
import sys, os
import argparse
import struct
import subprocess
from dataclasses import dataclass
from board import BOARDS, add_x86_hpet
from sdfgen import SystemDescription, Sddf, DeviceTree, Vmm
from importlib.metadata import version
from typing import Optional

assert version("sdfgen").split(".")[1] == "35", "Unexpected sdfgen version"

ProtectionDomain = SystemDescription.ProtectionDomain
VirtualMachine = SystemDescription.VirtualMachine
MemoryRegion = SystemDescription.MemoryRegion
CNode = SystemDescription.CNode
Map = SystemDescription.Map
CapMap = SystemDescription.CapMap
Channel = SystemDescription.Channel
IrqIoapic = SystemDescription.IrqIoapic


# @billn very hacky, resolve properly once PCI driver is merged in sDDF
# these need to match what the driver hardcoded
VIRTIO_NET_VQUEUES_PADDR = 0x7A00_0000
# these need to match what QEMU sets up, check readme for more info
VIRTIO_NET_PCI_BAR_PADDR = 0xFEBF_C000
VIRTIO_NET_PCI_IRQ = 10


def init_timer_system():
    if board.arch == SystemDescription.Arch.X86_64:
        timer_driver = ProtectionDomain(
            "timer_driver", "timer_driver.elf", priority=254
        )
        timer_system = Sddf.Timer(sdf, None, timer_driver)
        sdf.add_pd(timer_driver)
        add_x86_hpet(sdf, timer_driver)

        return timer_system

    return None


def init_serial_system(timer_system: Sddf.Timer):
    # Serial subsystem
    serial_driver = ProtectionDomain("serial_driver", "serial_driver.elf", priority=200)
    serial_virt_tx = ProtectionDomain(
        "serial_virt_tx", "serial_virt_tx.elf", priority=199
    )
    # Increase the stack size as running with UBSAN uses more stack space than normal.
    serial_virt_rx = ProtectionDomain(
        "serial_virt_rx", "serial_virt_rx.elf", priority=199, stack_size=0x2000
    )

    serial_node = None
    if board.arch != SystemDescription.Arch.X86_64:
        serial_node = dtb.node(board.serial)
        assert serial_node is not None

    serial_system = Sddf.Serial(
        sdf,
        serial_node,
        serial_driver,
        serial_virt_tx,
        virt_rx=serial_virt_rx,
        enable_color=True,
    )

    if board.arch == SystemDescription.Arch.X86_64:
        serial_port = SystemDescription.IoPort(0x3F8, 8, 0)
        serial_driver.add_ioport(serial_port)
        serial_irq = SystemDescription.IrqIoapic(0, 4, 0, id=1)
        serial_driver.add_irq(serial_irq)

    sdf.add_pd(serial_driver)
    sdf.add_pd(serial_virt_tx)
    sdf.add_pd(serial_virt_rx)

    return serial_system


def init_net_system(timer_system: Sddf.Timer, pci_driver: ProtectionDomain):
    # Net subsystem
    net_node = None
    if board.arch != SystemDescription.Arch.X86_64:
        net_node = dtb.node(board.ethernet)
        assert net_node is not None

    eth_driver = ProtectionDomain(
        "eth_driver", "eth_driver.elf", priority=101, budget=100, period=400
    )
    net_virt_tx = ProtectionDomain(
        "net_virt_tx", "network_virt_tx.elf", priority=100, budget=20000
    )
    net_virt_rx = ProtectionDomain("net_virt_rx", "network_virt_rx.elf", priority=99)
    vswitch = ProtectionDomain("net_vswitch", "network_vswitch.elf", priority=98)

    if board.name == "qemu_virt_x86":
        x86_virtio_net(eth_driver)
    elif board.name == "vb_105" or board.name == "viscous":
        x86_ixgbe_net(eth_driver)
        timer_system.add_client(eth_driver)

    net_system = Sddf.Net(
        sdf, net_node, eth_driver, net_virt_tx, net_virt_rx, vswitch=vswitch
    )
    sdf.add_pd(eth_driver)
    sdf.add_pd(net_virt_rx)
    sdf.add_pd(net_virt_tx)
    sdf.add_pd(vswitch)

    pci_driver.add_cap_map(CapMap(CapMap.CapType.Vspace, eth_driver, None, 2))
    pci_driver.add_cap_map(CapMap(CapMap.CapType.Cspace, eth_driver, None, 3))
    sdf.add_channel(Channel(pci_driver, eth_driver, a_id=1, b_id=10))

    return net_system, net_virt_tx


def x86_virtio_net(eth_driver):
    hw_net_rings = SystemDescription.MemoryRegion(
        sdf, "hw_net_rings", 0x10000, paddr=VIRTIO_NET_VQUEUES_PADDR
    )
    sdf.add_mr(hw_net_rings)
    hw_net_rings_map = SystemDescription.Map(hw_net_rings, 0x7000_0000, "rw", cached=False)
    eth_driver.add_map(hw_net_rings_map)

    virtio_net_regs = SystemDescription.MemoryRegion(
        sdf, "virtio_net_regs", 0x4000, paddr=VIRTIO_NET_PCI_BAR_PADDR
    )
    sdf.add_mr(virtio_net_regs)
    virtio_net_regs_map = SystemDescription.Map(
        virtio_net_regs, 0x6000_0000, "rw", cached=False
    )
    eth_driver.add_map(virtio_net_regs_map)

    virtio_net_irq = IrqIoapic(
        ioapic_id=0,
        pin=VIRTIO_NET_PCI_IRQ,
        vector=1,
        id=16,
        trigger=IrqIoapic.Trigger.LEVEL,
        polarity=IrqIoapic.Polarity.ACTIVELOW,
    )
    eth_driver.add_irq(virtio_net_irq)


def x86_ixgbe_net(eth_driver):
    # ixgbe_regs = MemoryRegion(
    #     sdf, name="eth_region_0", size=0x100000, paddr=board.ethernet
    # )
    # sdf.add_mr(ixgbe_regs)
    # eth_driver.add_map(
    #     Map(ixgbe_regs, vaddr=0x2000000, perms="rw", cached=False)
    # )

    # We can use `write-back` caching (i.e. cached=True) on x86 because the bus
    # will perform cache snooping in hardware, making it DMA coherent.
    hw_rx_ring_buffer = MemoryRegion(
        sdf, name="hw_rx_ring_buffer", size=0x4000, paddr=0x10000000
    )
    sdf.add_mr(hw_rx_ring_buffer)
    eth_driver.add_map(Map(hw_rx_ring_buffer, vaddr=0x2400000, perms="rw"))

    hw_tx_ring_buffer = MemoryRegion(
        sdf, name="hw_tx_ring_buffer", size=0x4000, paddr=0x10004000
    )
    sdf.add_mr(hw_tx_ring_buffer)
    eth_driver.add_map(Map(hw_tx_ring_buffer, vaddr=0x2404000, perms="rw"))

    # Legacy I/O APIC
    # eth_irq = SystemDescription.IrqIoapic(
    #     ioapic_id=0,
    #     pin=16,
    #     vector=8,
    #     trigger=IrqIoapic.Trigger.LEVEL,
    #     polarity=IrqIoapic.Polarity.ACTIVELOW,
    #     id=16,
    # )
    # eth_driver.add_irq(eth_irq)
    eth_driver.add_irq_placeholder(16)


def add_vm_client(
    client_id: int,
    cpu_id: int,
    serial_system: Sddf.Serial,
    net_system: Sddf.Net,
    timer_system: Sddf.Timer,
    client_dtb: Optional[DeviceTree],
):
    vmm_name = f"CLIENT_VMM{client_id}"
    vmm_elf = f"client_vmm{client_id}.elf"
    vm_name = f"client{client_id}_linux"

    vmm_client = ProtectionDomain(vmm_name, vmm_elf, priority=0, cpu=cpu_id, stack_size=0x4000)
    vm_client = VirtualMachine(vm_name, [VirtualMachine.Vcpu(id=0)])
    client = Vmm(sdf, vmm_client, vm_client, client_dtb)
    sdf.add_pd(vmm_client)

    serial_system.add_client(vmm_client)

    client_net_copier = ProtectionDomain(
        f"client{client_id}_net_copier", f"network_copy{client_id}.elf", priority=97, budget=20000
    )
    sdf.add_pd(client_net_copier)

    net_system.add_client_with_copier(
        vmm_client, copier=client_net_copier, vswitch=True
    )

    if board.arch == SystemDescription.Arch.X86_64:
        guest_ram_mr = MemoryRegion(sdf, name=f"guest{client_id}_ram", size=0x1000_0000)
        sdf.add_mr(guest_ram_mr)
        vmm_client.add_map(Map(guest_ram_mr, vaddr=0x20000000, perms="rw"))
        vm_client.add_map(Map(guest_ram_mr, vaddr=0x0, perms="rwx"))

        timer_system.add_client(vmm_client)

    return client, vmm_client, vm_client


class AcpiTablesConfig:
    def __init__(
        self,
        max_total_size: int,
    ):
        self.max_total_size = max_total_size
        self.patched_tables_end = 0
        self.alignment = 0x1000
        self.max_num_acpi_tables = 20 # This needs to be synced with MAX_NUM_ACPI_TABLES in acpi.h
        self.num_tables = 0
        self.acpi_table_bytes = bytearray()
        self.acpi_table_pointers = [0] * self.max_num_acpi_tables

    # TODO: add the checks
    def add_acpi_table(self, acpi_file):
        acpi_file = "/Users/terrybai/tmp/acpi_vb105/vb105_acpi/" + acpi_file + ".dat"
        print(acpi_file)
        assert os.path.isfile(acpi_file)
        with open(acpi_file, "rb") as data_file:
            byte_list = list(data_file.read())

            if len(byte_list) + len(self.acpi_table_bytes) < self.max_total_size:
                self.acpi_table_pointers[self.num_tables] = len(self.acpi_table_bytes)
                self.acpi_table_bytes.extend(byte_list)
                self.patched_tables_end = len(self.acpi_table_bytes)
                self.num_tables += 1

        trailing_len = len(self.acpi_table_bytes) % self.alignment
        if trailing_len != 0:
            padding_len = self.alignment - trailing_len
            if padding_len + len(self.acpi_table_bytes) < self.max_total_size:
                self.acpi_table_bytes.extend(b"\x00" * padding_len)

    def tables_serialise(self):
        pack_str = "<" + "B" * len(self.acpi_table_bytes)

        return struct.pack(
            pack_str,
            *self.acpi_table_bytes
        )

    def summary_serialise(self):
        pack_str = "<" + "Q" * self.max_num_acpi_tables + "QQII"

        return struct.pack(
            pack_str,
            *self.acpi_table_pointers,
            self.patched_tables_end,
            self.max_total_size,
            self.alignment,
            self.num_tables,
        )


def init_acpi_pci():
    acpi_driver = ProtectionDomain("acpi_driver", "acpi_driver.elf", priority=253, stack_size=0x5000)
    pci_driver = ProtectionDomain("pci_driver", "pci_driver.elf", priority=252)

    acpi_bootinfo_post_capdl_untypeds = MemoryRegion(sdf, "bootinfo_post_capdl_untypeds", 0x1000, prefill_bootinfo="post_capdl_untypeds")
    sdf.add_mr(acpi_bootinfo_post_capdl_untypeds)
    acpi_driver.add_map(Map(acpi_bootinfo_post_capdl_untypeds, 0x2000000, "r", setvar_vaddr="bootinfo_post_capdl_untypeds"))

    acpi_bootinfo_rsdp = MemoryRegion(sdf, "bootinfo_rsdp", 0x1000, prefill_bootinfo="x86_acpi_rsdp")
    sdf.add_mr(acpi_bootinfo_rsdp)
    acpi_driver.add_map(Map(acpi_bootinfo_rsdp, 0x2001000, "r", setvar_vaddr="bootinfo_rsdp"))

    acpi_tables_config = AcpiTablesConfig(0x500000)

    cnode_remaining_untypeds = CNode("remaining_untypeds", True, 9)
    sdf.add_cnode(cnode_remaining_untypeds)
    acpi_driver.add_cap_map(CapMap(CapMap.CapType.Cnode, None, cnode_remaining_untypeds, 1))
    acpi_driver.add_cap_map(CapMap(CapMap.CapType.Vspace, pci_driver, None, 2))

    cnode_pci_resources = CNode("pci_resources", False, 9)
    sdf.add_cnode(cnode_pci_resources)
    acpi_driver.add_cap_map(CapMap(CapMap.CapType.Cnode, None, cnode_pci_resources, 3))
    pci_driver.add_cap_map(CapMap(CapMap.CapType.Cnode, None, cnode_pci_resources, 1))

    mr_aml_object_pool = MemoryRegion(sdf, "aml_object_pool", 0x100000)
    sdf.add_mr(mr_aml_object_pool)
    acpi_driver.add_map(Map(mr_aml_object_pool, 0x30000000, "rw"))

    mr_aml_state_stack = MemoryRegion(sdf, "aml_state_stack", 0x10000)
    sdf.add_mr(mr_aml_state_stack)
    acpi_driver.add_map(Map(mr_aml_state_stack, 0x50000000, "rw"))

    mr_acpi_tables_copy = MemoryRegion(sdf, "acpi_tables_copy", 0x50000)
    sdf.add_mr(mr_acpi_tables_copy)
    acpi_driver.add_map(Map(mr_acpi_tables_copy, 0x40000000, "rw"))

    mr_pci_resources = MemoryRegion(sdf, "pci_resources", 0x40000)
    sdf.add_mr(mr_pci_resources)
    acpi_driver.add_map(Map(mr_pci_resources, 0x60000000, "rw", cached=False))
    pci_driver.add_map(Map(mr_pci_resources, 0x60000000, "rw", cached=False))

    sdf.add_channel(Channel(acpi_driver, pci_driver, a_id=0, b_id=0))
    sdf.add_pd(acpi_driver)
    sdf.add_pd(pci_driver)

    return acpi_driver, pci_driver, acpi_tables_config


# Assumes elf string has ".elf" suffix, adds ".data" to data string
def update_elf_section(
    elf_name: str, section_name: str, data_name: str, data_number=None
):
    assert os.path.isfile(elf_name)
    if data_number != None:
        data_name += str(data_number)
    data_name += ".data"
    assert os.path.isfile(data_name)
    assert (
        subprocess.run(
            [
                obj_copy,
                "--update-section",
                "." + section_name + "=" + data_name,
                elf_name,
            ]
        ).returncode
        == 0
    )


def generate(
    sdf_file: str,
    output_dir: str,
    dtb: Optional[DeviceTree],
    client_dtb: Optional[DeviceTree],
):
    acpi_driver, pci_driver, acpi_tables_config = init_acpi_pci()
    timer_system = init_timer_system()
    serial_system = init_serial_system(timer_system)
    net_system, net_virt_tx = init_net_system(timer_system, pci_driver)

    client0, vmm_client0, vm_client0 = add_vm_client(0, 0, serial_system, net_system, timer_system, client_dtb)
    client1, vmm_client1, vm_client1 = add_vm_client(1, 1, serial_system, net_system, timer_system, client_dtb)
    client2, vmm_client2, vm_client2 = add_vm_client(2, 2, serial_system, net_system, timer_system, client_dtb)
    client3, vmm_client3, vm_client3 = add_vm_client(3, 3, serial_system, net_system, timer_system, client_dtb)

    if timer_system:
        assert timer_system.connect()
        assert timer_system.serialise_config(output_dir)

    assert serial_system.connect()
    assert serial_system.serialise_config(output_dir)
    assert net_system.connect()

    # Add ACLs - by default bidirectional
    # 0 <-> 1, 3, V
    # 1 <-> 0, 3, V
    # 2 <-> V
    # 3 <-> 0, 1, V
    net_system.add_acl_rule(vmm_client0, vmm_client3)
    net_system.add_acl_rule(vmm_client0, net_virt_tx)
    net_system.add_acl_rule(vmm_client1, vmm_client0)
    net_system.add_acl_rule(vmm_client1, net_virt_tx)
    net_system.add_acl_rule(vmm_client2, net_virt_tx)
    net_system.add_acl_rule(vmm_client3, vmm_client0)
    net_system.add_acl_rule(vmm_client3, vmm_client1)
    net_system.add_acl_rule(vmm_client3, net_virt_tx)

    assert net_system.serialise_config(output_dir)
    assert client0.connect()
    assert client0.serialise_config(output_dir)
    assert client1.connect()
    assert client1.serialise_config(output_dir)
    assert client2.connect()
    assert client2.serialise_config(output_dir)
    assert client3.connect()
    assert client3.serialise_config(output_dir)

    with open(f"{output_dir}/{sdf_file}", "w+") as f:
        f.write(sdf.render())

    with open(f"{output_dir}/acpi_tables_summary.data", "wb+") as f:
        f.write(acpi_tables_config.summary_serialise())
    update_elf_section("acpi_driver.elf", "acpi_tables_summary", "acpi_tables_summary")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dtb", required=False)
    parser.add_argument("--client-dtb", required=False)
    parser.add_argument("--sddf", required=True)
    parser.add_argument("--board", required=True, choices=[b.name for b in BOARDS])
    parser.add_argument("--output", required=True)
    parser.add_argument("--objcopy", required=True)
    parser.add_argument("--sdf", required=True)

    args = parser.parse_args()

    board = next(filter(lambda b: b.name == args.board, BOARDS))

    paddr_top = board.paddr_top
    if board.arch == SystemDescription.Arch.X86_64:
        # We don't use the value from sDDF common files so that we have
        # freedom to move memory regions around.
        paddr_top = 0x5000_0000

    sdf = SystemDescription(board.arch, paddr_top)

    sddf = Sddf(args.sddf)

    global obj_copy
    obj_copy = args.objcopy

    dtb = None
    client_dtb = None
    if board.arch != SystemDescription.Arch.X86_64:
        if args.dtb is None or args.client_dtb is None:
            print("--dtb and --client-dtb must be provided for non x86 targets")

        with open(args.dtb, "rb") as f:
            dtb = DeviceTree(f.read())

        with open(args.client_dtb, "rb") as f:
            client_dtb = DeviceTree(f.read())

    generate(args.sdf, args.output, dtb, client_dtb)
