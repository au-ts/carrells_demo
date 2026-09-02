#
# Copyright 2026, UNSW
#
# SPDX-License-Identifier: BSD-2-Clause
#

PYTHON ?= python3
IASL ?= iasl
TOOLCHAIN ?= clang
LINUX ?= ad68a1c839149465454d059b32fb2a3593404268-linux
INITRD ?= a0b53ecb5c7d68a1c89b843d3ad07508ba9af9a3-rootfs.cpio.gz
LIBVMM_DOWNLOADS := https://trustworthy.systems/Downloads/libvmm/images/

BUILD_DIR := $(abspath ${BUILD_DIR})
MICROKIT_CONFIG ?= smp-debug
BOARD_DIR := $(MICROKIT_SDK)/board/$(MICROKIT_BOARD)/$(MICROKIT_CONFIG)

SUPPORTED_BOARDS := x86_64_generic_vtx
ETH_DRIVER := $(SDDF)/drivers/network/$(ETH_DRIVER)

include ${SDDF}/tools/make/board/common.mk

ifneq ($(ARCH),x86_64)
$(error Unsupported architecture $(ARCH))
endif

SYSTEM_FILE := carrells.system
IMAGE_FILE := loader.img
REPORT_FILE := report.txt
LIBVMM_TOOLS := $(LIBVMM)/tools
MICROKIT_TOOL = $(MICROKIT_SDK)/bin/microkit
METAPROGRAM := $(CARRELLS_EXAMPLE)/meta.py

SDDF_CUSTOM_LIBC := 1

vpath %.c $(SDDF) $(LIBVMM) $(CARRELLS_EXAMPLE)

CFLAGS += \
	  -Wall \
	  -Wno-unused-function \
	  -DBOARD_$(MICROKIT_BOARD) \
	  -DSDDF_VIRTIO_PCI_TRANSPORT_SKIP_BUS_CHECK \
	  -I$(BOARD_DIR)/include \
	  -I$(SDDF)/include \
	  -I$(SDDF)/include/microkit \
	  -I$(LIBVMM)/include \
	  -I$(CARRELLS_EXAMPLE)/include

LDFLAGS := -L$(BOARD_DIR)/lib
LIBS := --start-group -lmicrokit -Tmicrokit.ld libsddf_util_debug.a --end-group

include $(SDDF)/util/util.mk
include $(SDDF)/serial/components/serial_components.mk
include ${SDDF}/drivers/serial/${UART_DRIV_DIR}/serial_driver.mk
include ${SDDF}/drivers/network/${NET_DRIV_DIR}/eth_driver.mk
include $(SDDF)/network/components/network_components.mk
include ${SDDF}/drivers/timer/${TIMER_DRIV_DIR}/timer_driver.mk
include $(LIBVMM)/vmm.mk
include $(LIBVMM_TOOLS)/linux/net/net_init.mk
include $(CARRELLS_EXAMPLE)/vmm.mk
include ${SDDF}/drivers/acpi/acpi_driver.mk
include ${SDDF}/drivers/pci/pci_driver.mk

IMAGES = client_vmm.elf timer_driver.elf serial_driver.elf \
		serial_virt_tx.elf serial_virt_rx.elf network_virt_rx.elf \
		network_virt_tx.elf eth_driver.elf network_copy.elf \
		network_vswitch.elf timer_driver.elf acpi_driver.elf \
		pci_driver.elf

CHECK_FLAGS_BOARD_MD5 := .board_cflags-$(shell echo -- $(CFLAGS) $(BOARD) $(MICROKIT_CONFIG) | shasum | sed 's/ *-//')
$(CHECK_FLAGS_BOARD_MD5):
	-rm -f .board_cflags-*
	touch $@

all: $(IMAGE_FILE)

$(IMAGES): libsddf_util_debug.a

$(SYSTEM_FILE): $(METAPROGRAM) $(IMAGES) |$(BUILD_DIR)
	cp client_vmm.elf client_vmm0.elf
	cp client_vmm.elf client_vmm1.elf
	cp client_vmm.elf client_vmm2.elf
	cp client_vmm.elf client_vmm3.elf
	cp network_copy.elf network_copy0.elf
	cp network_copy.elf network_copy1.elf
	cp network_copy.elf network_copy2.elf
	cp network_copy.elf network_copy3.elf
	PYTHONPATH=${SDDF}/tools/meta:$$PYTHONPATH $(PYTHON) $(METAPROGRAM) --sddf $(SDDF) --board $(X86_BOARD) --objcopy $(OBJCOPY) --output . --sdf $(SYSTEM_FILE) $(PARTITION_ARG)
	$(OBJCOPY) --update-section .device_resources=timer_driver_device_resources.data timer_driver.elf
	$(OBJCOPY) --update-section .timer_client_config=timer_client_CLIENT_VMM0.data client_vmm0.elf
	$(OBJCOPY) --update-section .timer_client_config=timer_client_CLIENT_VMM1.data client_vmm1.elf
	$(OBJCOPY) --update-section .timer_client_config=timer_client_CLIENT_VMM2.data client_vmm2.elf
	$(OBJCOPY) --update-section .timer_client_config=timer_client_CLIENT_VMM3.data client_vmm3.elf
	$(OBJCOPY) --update-section .device_resources=serial_driver_device_resources.data serial_driver.elf
	$(OBJCOPY) --update-section .serial_driver_config=serial_driver_config.data serial_driver.elf
	$(OBJCOPY) --update-section .serial_virt_rx_config=serial_virt_rx.data serial_virt_rx.elf
	$(OBJCOPY) --update-section .serial_virt_tx_config=serial_virt_tx.data serial_virt_tx.elf
	$(OBJCOPY) --update-section .serial_client_config=serial_client_CLIENT_VMM0.data client_vmm0.elf
	$(OBJCOPY) --update-section .serial_client_config=serial_client_CLIENT_VMM1.data client_vmm1.elf
	$(OBJCOPY) --update-section .serial_client_config=serial_client_CLIENT_VMM2.data client_vmm2.elf
	$(OBJCOPY) --update-section .serial_client_config=serial_client_CLIENT_VMM3.data client_vmm3.elf
	$(OBJCOPY) --update-section .vmm_config=vmm_CLIENT_VMM0.data client_vmm0.elf
	$(OBJCOPY) --update-section .vmm_config=vmm_CLIENT_VMM1.data client_vmm1.elf
	$(OBJCOPY) --update-section .vmm_config=vmm_CLIENT_VMM2.data client_vmm2.elf
	$(OBJCOPY) --update-section .vmm_config=vmm_CLIENT_VMM3.data client_vmm3.elf
	$(OBJCOPY) --update-section .device_resources=eth_driver_device_resources.data eth_driver.elf
	$(OBJCOPY) --update-section .net_driver_config=net_driver.data eth_driver.elf
	$(OBJCOPY) --update-section .net_virt_rx_config=net_virt_rx.data network_virt_rx.elf
	$(OBJCOPY) --update-section .net_virt_tx_config=net_virt_tx.data network_virt_tx.elf
	$(OBJCOPY) --update-section .net_copy_config=net_copy_client0_net_copier.data network_copy0.elf
	$(OBJCOPY) --update-section .net_copy_config=net_copy_client1_net_copier.data network_copy1.elf
	$(OBJCOPY) --update-section .net_copy_config=net_copy_client2_net_copier.data network_copy2.elf
	$(OBJCOPY) --update-section .net_copy_config=net_copy_client3_net_copier.data network_copy3.elf
	$(OBJCOPY) --update-section .net_client_config=net_client_CLIENT_VMM0.data client_vmm0.elf
	$(OBJCOPY) --update-section .net_client_config=net_client_CLIENT_VMM1.data client_vmm1.elf
	$(OBJCOPY) --update-section .net_client_config=net_client_CLIENT_VMM2.data client_vmm2.elf
	$(OBJCOPY) --update-section .net_client_config=net_client_CLIENT_VMM3.data client_vmm3.elf
	$(OBJCOPY) --update-section .net_vswitch_config=net_vswitch.data network_vswitch.elf

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

SPEC = capdl_spec.json
$(IMAGE_FILE) $(REPORT_FILE): $(IMAGES) $(SYSTEM_FILE)
	$(MICROKIT_TOOL) $(SYSTEM_FILE) --search-path $(BUILD_DIR) --board $(MICROKIT_BOARD) \
		--config $(MICROKIT_CONFIG) -o $(IMAGE_FILE) -r $(REPORT_FILE) --capdl-json ${SPEC}

clean::
	$(RM) -f *.elf .depend* $
	find . -name \*.[do] -type f |xargs --no-run-if-empty rm

clobber:: clean
	rm -f *.a
	rm -f $(IMAGE_FILE) $(REPORT_FILE)

FORCE:
