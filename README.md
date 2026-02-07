# CMPRSS (Compress)

A privacy-first, microservices-based PDF compression tool running on bare metal.
**Built on Linux. 100% Private. No Logs.**

## 🏗 Architecture
This project utilizes a distributed microservices architecture orchestrated by Kubernetes (K3s).

* **Ingress:** Cloudflare Tunnel (Zero Trust) with self-healing Liveness Probes.
* **Frontend:** Flask (Python) - Lightweight web server.
* **Message Broker:** Redis - Handles job queues and decoupling.
* **Worker:** Python + Ghostscript - Dedicated container for PDF processing.
* **Storage:** Ephemeral shared volumes.

## 🛡 Privacy Philosophy
* **No Databases:** We do not store user data.
* **Auto-Wipe:** A "Janitor" CronJob runs hourly to obliterate all uploaded files.
* **Anonymous:** No accounts, no tracking pixels, no cookies.

## 💰 Support
Maintained by **Nadim Elie**.

* **BTC:** `bc1qvqqvl774t3hu0fnmr72lqv3dks3v3yhx3fsxzx`

## 🚀 Deployment

### Prerequisites
* Docker & Kubernetes (K3s)
* Cloudflare Tunnel Token

### Build & Run
```bash
# Build the image
docker build -t docker.io/nadimelie/cmprss:latest .

# Deploy to Kubernetes
kubectl apply -f deployment.yaml
