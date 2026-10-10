# Hardware inventory

## Evidence and scope

The production Ansible inventory at [`bare/inventories/prod.yml`](../bare/inventories/prod.yml) declares three hosts (`bare0`, `bare1`, and `bare2`), with one master and two workers. Hardware details below combine the owner's information with read-only osquery results collected from all three production hosts on 2026-10-10. The collection used the repository's approved `hardware` query category and wrote sanitized snapshots outside Git; no host configuration was changed.

## Hardware inventory

| Inventory host | System | Processor | CPU cores | Memory reported by osquery |
|---|---|---|---|---|
| `bare0` (master) | HP EliteDesk 800 G2 | Intel Core i5-6500T @ 2.50 GHz | 4 physical / 4 logical | 7.64 GiB |
| `bare1` (worker) | HP EliteDesk 800 G2 | Intel Core i5-6500T @ 2.50 GHz | 4 physical / 4 logical | 7.64 GiB |
| `bare2` (worker) | HP EliteDesk 800 G2 | Intel Core i5-6500T @ 2.50 GHz | 4 physical / 4 logical | 7.64 GiB |

The system model comes from the owner. Processor, core counts, and memory are from the live read-only audit; `physical_memory_gib` reports 7.64 GiB on each host. Storage devices/capacity are not included here because the hardware query result did not provide usable device identification/capacity facts.

## Updating this record

For future inventory updates, use the approved read-only osquery collector described in the [OS lifecycle guide](maintenance/os-lifecycle.md), correlate each sanitized result to its inventory alias, and keep raw snapshots outside the repository. Do not include serial numbers, MAC addresses, or other sensitive identifiers unless there is a clear need to publish them.
