# Homelab hardware

The bare-metal Kubernetes cluster runs on three HP EliteDesk 800 G2 mini PCs:

| Host | Role | Processor | CPU cores | RAM |
|---|---|---|---|---|
| `bare0` | Master | Intel Core i5-6500T @ 2.50 GHz | 4 cores / 4 threads | 8 GB |
| `bare1` | Worker | Intel Core i5-6500T @ 2.50 GHz | 4 cores / 4 threads | 8 GB |
| `bare2` | Worker | Intel Core i5-6500T @ 2.50 GHz | 4 cores / 4 threads | 8 GB |

Host groups are defined in [`bare/inventories/prod.yml`](../bare/inventories/prod.yml).