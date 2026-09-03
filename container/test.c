/*
 * Copyright 2026, UNSW
 *
 * SPDX-License-Identifier: BSD-2-Clause
 */

#include <microkit.h>
#include <sddf/serial/queue.h>
#include <sddf/serial/config.h>
#include <sddf/network/queue.h>
#include <sddf/network/config.h>
#include <sddf/util/printf.h>

__attribute__((__section__(".serial_client_config"))) serial_client_config_t serial_config;
__attribute__((__section__(".net_client_config"))) net_client_config_t net_config;

/* sDDF data */
serial_queue_handle_t serial_rx_queue;
serial_queue_handle_t serial_tx_queue;

net_queue_handle_t net_rx_queue;
net_queue_handle_t net_tx_queue;

void init(void)
{
    /* Initialise sDDF Serial subsystem. */
    serial_queue_init(&serial_rx_queue, serial_config.rx.queue.vaddr, serial_config.rx.data.size,
                      serial_config.rx.data.vaddr);
    serial_queue_init(&serial_tx_queue, serial_config.tx.queue.vaddr, serial_config.tx.data.size,
                      serial_config.tx.data.vaddr);

    /* Initialise sDDF Network subsystem. */
    net_queue_init(&net_rx_queue, net_config.rx.free_queue.vaddr, net_config.rx.active_queue.vaddr,
                   net_config.rx.num_buffers);
    net_queue_init(&net_tx_queue, net_config.tx.free_queue.vaddr, net_config.tx.active_queue.vaddr,
                   net_config.tx.num_buffers);
    net_buffers_init(&net_tx_queue, 0);

    sddf_dprintf("Container started\n");
}

void notified(microkit_channel ch)
{
}
