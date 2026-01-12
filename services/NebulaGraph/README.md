NebulaGraph via Docker Compose

Overview
- Three services: metad, storaged, graphd
- Single-host setup suitable for local/dev use
- Optional Nebula Graph Studio UI on port 7001
- Ports: graphd Thrift on 9669 (clients connect here)

Prereqs
- Docker Engine + Compose v2

Quick start
1) Initialize directory and env:
   mkdir -p data/meta data/storage logs/{metad,storaged,graphd}
   cp .env.example .env
   # Optionally pin NEBULA_VERSION in .env

2) Start NebulaGraph:
   docker compose up -d
   docker compose ps

3) Connect (CLI):
   docker run --rm -it --network host vesoft/nebula-console:latest \
     -addr 127.0.0.1 -port 9669 -u root -p nebula

4) Use Nebula Graph Studio (Web UI):
  Open http://localhost:7001
  Connect to graphd at host: graphd, port: 9669, user: root, password: nebula

Notes
- Default credentials are root/nebula (change as needed in production).
- Logs and data are bind-mounted under ./logs and ./data; ensure disk space.
- For multi-host or production, consult NebulaGraph docs for cluster setup and advanced configuration.
- If you see image pull timeouts, configure Docker registry mirrors on the host and retry:
  /etc/docker/daemon.json:
  {
    "registry-mirrors": [
      "https://mirror.ccs.tencentyun.com",
      "https://docker.m.daocloud.io",
      "https://hub-mirror.c.163.com"
    ]
  }
  systemctl daemon-reload && systemctl restart docker

Maintenance
- Update images: docker compose pull && docker compose up -d
- View logs: docker compose logs -f graphd
- Stop: docker compose down
