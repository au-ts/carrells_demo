#
# Copyright 2026, UNSW
#
# SPDX-License-Identifier: BSD-2-Clause
#

.PHONY: container
container:
	mkdir -p container

CONTAINER = $(CARRELLS_EXAMPLE)/container

container/test.o: $(CONTAINER)/test.c $(CHECK_FLAGS_BOARD_MD5) |
	$(CC) $(CFLAGS) -c -o $@ $<

container.elf: container/test.o |container
	$(LD) $(LDFLAGS) $^ $(LIBS) -o $@
