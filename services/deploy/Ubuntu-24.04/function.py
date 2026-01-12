#!/usr/bin/env python3
import os
import json
import subprocess
import sys
from typing import Any, Dict, List

# ---- Utility helpers ----

def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, stdout=sys.stdout, stderr=sys.stderr)


def run_sh(cmd: str) -> None:
    run(["bash", "-lc", cmd])


def fetch_with_retry(url: str, dest: str, retries: int = 6, delay: int = 3) -> None:
    for attempt in range(1, retries + 1):
        try:
            run(["curl", "-fL", "--retry", "3", "--retry-delay", "1", "--retry-all-errors", "-4", url, "-o", dest])
            return
        except subprocess.CalledProcessError:
            if attempt == retries:
                raise
            print(f"[WARN] Download failed (attempt {attempt}/{retries}) for {url}; retrying in {delay}s...", file=sys.stderr)
            run(["sleep", str(delay)], check=True)


def fetch_gpg_key(url: str, dest: str) -> None:
    tmp = "/tmp/key.tmp"
    fetch_with_retry(url, tmp)
    run(["gpg", "--dearmor", "-o", dest, tmp])
    os.chmod(dest, 0o644)
    try:
        os.remove(tmp)
    except Exception:
        pass


def ensure_gpg_key_present(dest: str, urls: List[str]) -> None:
    if not (os.path.exists(dest) and os.path.getsize(dest) > 0):
        for u in urls:
            try:
                fetch_gpg_key(u, dest)
                return
            except Exception:
                print(f"[WARN] Failed to fetch key from {u}, trying next if available", file=sys.stderr)
        raise RuntimeError(f"All key URLs failed for {dest}")


def install_base_packages() -> None:
    run(["apt-get", "update", "-y"])  # noqa: S603,S607
    run(["apt-get", "install", "-y", "ca-certificates", "curl", "gnupg", "lsb-release", "apt-transport-https", "software-properties-common"])  # noqa: S603,S607


# ---- Install implementations ----

def configure_docker_registry_mirrors(mirrors: List[str]) -> None:
    if not mirrors:
        return
    os.makedirs("/etc/docker", exist_ok=True)
    path = "/etc/docker/daemon.json"
    data: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    data["registry-mirrors"] = mirrors
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    run(["systemctl", "daemon-reload"], check=False)
    run(["systemctl", "restart", "docker"], check=False)
    print(f"[INFO] Configured Docker registry mirrors: {', '.join(mirrors)}")

def install_docker(cfg: Dict[str, Any]) -> None:
    gpg_urls = cfg.get("docker_gpg_urls")
    repo_urls = cfg.get("docker_repo_urls")
    if not gpg_urls or not repo_urls:
        print("[ERROR] docker config requires docker_gpg_urls and docker_repo_urls.", file=sys.stderr)
        sys.exit(1)
    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    os.makedirs("/etc/apt/keyrings", exist_ok=True)
    docker_key = "/etc/apt/keyrings/docker.gpg"
    # Reset previous
    for f in (docker_key, "/etc/apt/sources.list.d/docker.list"):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    ensure_gpg_key_present(docker_key, gpg_urls)
    with open("/etc/apt/sources.list.d/docker.list", "w", encoding="utf-8") as f:
        f.write(f"deb [arch={arch} signed-by=/etc/apt/keyrings/docker.gpg] {repo_urls[0]} noble stable\n")
    print(f"[INFO] Docker repo set to {repo_urls[0]} (arch={arch})")

    run(["apt-get", "update", "-y"])  # noqa: S603,S607
    run(["apt-get", "install", "-y", "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"])  # noqa: S603,S607
    run(["systemctl", "enable", "--now", "docker", "containerd"])  # noqa: S603

    if not os.path.exists("/etc/containerd/config.toml"):
        run_sh("containerd config default | tee /etc/containerd/config.toml >/dev/null")
    run(["sed", "-i", "s/^SystemdCgroup = false/SystemdCgroup = true/", "/etc/containerd/config.toml"])  # noqa: S603
    run(["systemctl", "restart", "containerd"])  # noqa: S603

    mirrors = cfg.get("registry_mirrors") or []
    if mirrors:
        configure_docker_registry_mirrors(mirrors)


def install_docker_compose(cfg: Dict[str, Any]) -> None:
    run(["apt-get", "update", "-y"])  # noqa: S603,S607
    run(["apt-get", "install", "-y", "docker-compose-plugin"])  # noqa: S603,S607
    try:
        run(["docker", "compose", "version"], check=False)
    except Exception:
        pass


def install_kernel(cfg: Dict[str, Any]) -> None:
    with open("/etc/modules-load.d/k8s.conf", "w", encoding="utf-8") as f:
        f.write("overlay\nbr_netfilter\n")
    run(["modprobe", "overlay"])  # noqa: S603
    run(["modprobe", "br_netfilter"])  # noqa: S603
    with open("/etc/sysctl.d/99-kubernetes-cri.conf", "w", encoding="utf-8") as f:
        f.write("""net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
""")
    run(["sysctl", "--system"])  # noqa: S603


def install_swap(cfg: Dict[str, Any]) -> None:
    if cfg.get("disable", True):
        run(["swapoff", "-a"])  # noqa: S603
        run(["sed", "-ri", r"/\\s+swap\\s+/s/^/#/", "/etc/fstab"])  # noqa: S603


def install_kubernetes(cfg: Dict[str, Any]) -> None:
    k8s_version = cfg.get("k8s_version")
    gpg_urls = cfg.get("k8s_gpg_urls")
    if not k8s_version:
        k8s_version = os.environ.get("K8S_VERSION") or "1.30"
    if not gpg_urls:
        gpg_urls = [f"https://pkgs.k8s.io/core:/stable:/v{k8s_version}/deb/Release.key"]
    os.makedirs("/etc/apt/keyrings", exist_ok=True)
    ensure_gpg_key_present("/etc/apt/keyrings/kubernetes-apt-keyring.gpg", gpg_urls)
    with open("/etc/apt/sources.list.d/kubernetes.list", "w", encoding="utf-8") as f:
        f.write(f"deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v{k8s_version}/deb/ /\n")
    run(["apt-get", "update", "-y"])  # noqa: S603,S607
    run(["apt-get", "install", "-y", "kubelet", "kubeadm", "kubectl"])  # noqa: S603,S607
    run(["apt-mark", "hold", "kubelet", "kubeadm", "kubectl"])  # noqa: S603
    run(["systemctl", "enable", "--now", "kubelet"])  # noqa: S603


# ---- Uninstall implementations ----

def uninstall_kubernetes(cfg: Dict[str, Any]) -> None:
    run(["kubeadm", "reset", "-f"], check=False)
    run(["apt-get", "purge", "-y", "kubelet", "kubeadm", "kubectl"], check=False)
    run(["apt-mark", "unhold", "kubelet", "kubeadm", "kubectl"], check=False)
    run(["apt-get", "autoremove", "-y"], check=False)
    for f in ("/etc/apt/sources.list.d/kubernetes.list", "/etc/apt/keyrings/kubernetes-apt-keyring.gpg"):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def uninstall_docker_compose(cfg: Dict[str, Any]) -> None:
    run(["apt-get", "purge", "-y", "docker-compose-plugin"], check=False)


def uninstall_docker(cfg: Dict[str, Any]) -> None:
    run(["systemctl", "stop", "docker", "containerd"], check=False)
    run(["apt-get", "purge", "-y", "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"], check=False)
    run(["apt-get", "autoremove", "-y"], check=False)
    for p in ("/var/lib/docker", "/var/lib/containerd"):
        run(["rm", "-rf", p], check=False)
    for f in ("/etc/apt/sources.list.d/docker.list", "/etc/apt/keyrings/docker.gpg"):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def uninstall_kernel(cfg: Dict[str, Any]) -> None:
    for f in ("/etc/modules-load.d/k8s.conf", "/etc/sysctl.d/99-kubernetes-cri.conf"):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def uninstall_swap(cfg: Dict[str, Any]) -> None:
    # No-op; swap re-enable left to operator.
    pass
