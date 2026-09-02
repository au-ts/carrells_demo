#
# Copyright 2026, UNSW
#
# SPDX-License-Identifier: BSD-2-Clause
#

.PHONY: client_vm
client_vm:
	mkdir -p client_vm

CLIENT_VM = $(CARRELLS_EXAMPLE)/client_vm

CLIENT_VM_USERLEVEL_INIT := net_client_init

${LINUX}:
	curl -L ${LIBVMM_DOWNLOADS}/$(LINUX).tar.gz -o $(LINUX).tar.gz
	mkdir -p linux_download_dir
	tar -xf $@.tar.gz -C linux_download_dir
ifeq ($(ARCH),aarch64)
	cp linux_download_dir/${LINUX}/Image ${LINUX}
else ifeq ($(ARCH),x86_64)
	cp linux_download_dir/${LINUX}/bzImage ${LINUX}
endif

${INITRD}:
	curl -L ${LIBVMM_DOWNLOADS}/$(INITRD).tar.gz -o $(INITRD).tar.gz
	mkdir -p initrd_download_dir
	tar xf $@.tar.gz -C initrd_download_dir
	cp initrd_download_dir/${INITRD}/rootfs.cpio.gz ${INITRD}

client_vm/rootfs.cpio.gz: ${INITRD} \
	$(CLIENT_VM_USERLEVEL_INIT) $(CLIENT_VM_USERLEVEL_HOME) |client_vm
	$(LIBVMM)/tools/packrootfs ${INITRD} \
		client_vm/rootfs_staging -o $@ \
		--startup $(CLIENT_VM_USERLEVEL_INIT) \
		--home $(CLIENT_VM_USERLEVEL_HOME)

client_vm/vm_dsdt.aml: $(CLIENT_VM)/carrells_dsdt.dsl |client_vm
	$(IASL) -p $@ $^

client_vm/vmm.o: $(CLIENT_VM)/client_vmm.c $(CHECK_FLAGS_BOARD_MD5) |client_vm
	$(CC) $(CFLAGS) -c -o $@ $<

client_vm/guest_arch_init.o: $(CLIENT_VM)/guest_arch_init.c $(CHECK_FLAGS_BOARD_MD5) |client_vm
	$(CC) $(CFLAGS) -c -o $@ $<

client_vm/images.o: $(LIBVMM)/tools/package_guest_images.S ${LINUX} $(CHECK_FLAGS_BOARD_MD5) \
	                client_vm/vm_dsdt.aml client_vm/rootfs.cpio.gz
	$(CC) -c -g3 -x assembler-with-cpp \
					-DGUEST_KERNEL_IMAGE_PATH=\"${LINUX}\" \
					-DGUEST_DSDT_AML_PATH=\"client_vm/vm_dsdt.aml\" \
					-DGUEST_INITRD_IMAGE_PATH=\"client_vm/rootfs.cpio.gz\" \
					-target $(TARGET) \
					$(LIBVMM)/tools/package_guest_images.S -o $@

client_vmm.elf: client_vm/vmm.o client_vm/guest_arch_init.o client_vm/images.o libvmm.a |client_vm
	$(LD) $(LDFLAGS) $^ $(LIBS) -o $@
