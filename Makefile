#
# Copyright 2026, UNSW
#
# SPDX-License-Identifier: BSD-2-Clause
#

BUILD_DIR ?= build
export MICROKIT_CONFIG ?= smp-debug

ifeq ($(strip $(MICROKIT_SDK)),)
$(error MICROKIT_SDK must be specified)
endif
override MICROKIT_SDK := $(abspath $(MICROKIT_SDK))

ifeq ($(findstring smp-,$(MICROKIT_CONFIG)),)
$(error MICROKIT_CONFIG must be one of smp-debug, smp-release or smp-benchmark)
endif

BUILD_DIR ?= build
export BUILD_DIR := $(abspath ${BUILD_DIR})
export CARRELLS_EXAMPLE := $(abspath .)

export MICROKIT_TOOL ?= $(MICROKIT_SDK)/bin/microkit
export SDDF := $(abspath ./dep/sddf)
export LIBVMM := $(abspath ./dep/libvmm)
export LIONSOS := $(abspath ./dep/lionsos)

IMAGE_FILE := $(BUILD_DIR)/loader.img
REPORT_FILE := $(BUILD_DIR)/report.txt

all: $(IMAGE_FILE)

qemu $(IMAGE_FILE) $(REPORT_FILE) clean clobber: $(BUILD_DIR)/Makefile FORCE
	$(MAKE) -C $(BUILD_DIR) MICROKIT_SDK=$(MICROKIT_SDK) $(notdir $@)

$(BUILD_DIR)/Makefile: carrells.mk
	mkdir -p $(BUILD_DIR)
	cp carrells.mk $@

FORCE:
