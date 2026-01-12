# Ubuntu 24.04 Backend Deployment

This directory holds backend deployment assets for Ubuntu 24.04 servers. The `deploy.sh` script installs Docker, containerd, and Kubernetes (kubelet/kubeadm/kubectl) with defaults suitable for kubeadm-managed clusters.

## Usage

```bash
# From this directory
sudo bash deploy.sh           # installs Kubernetes 1.30 by default
K8S_VERSION=1.31 sudo bash deploy.sh  # install a specific minor release


# Mirror override example (Tencent – now the default):
DOCKER_GPG_URL=https://mirrors.tencentyun.com/docker-ce/linux/ubuntu/gpg \
DOCKER_REPO_URL=https://mirrors.tencentyun.com/docker-ce/linux/ubuntu \
K8S_GPG_URL=https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key \
sudo bash deploy.sh

# JSON-driven config (env still wins over JSON):
# Create settings.json alongside the script, e.g.:
# {
#   "k8s_version": "1.30",
#   "docker_gpg_urls": [
#     "https://download.docker.com/linux/ubuntu/gpg",
#     "https://mirrors.tencentyun.com/docker-ce/linux/ubuntu/gpg"
#   ],
#   "docker_repo_urls": [
#     "https://download.docker.com/linux/ubuntu",
#     "https://mirrors.tencentyun.com/docker-ce/linux/ubuntu"
#   ],
#   "k8s_gpg_urls": [
#     "https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key"
#   ]
# }
# Then run:
# CONFIG_JSON=./settings.json sudo bash deploy.sh
