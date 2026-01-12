Matrix (Synapse + Element) via Docker Compose

Overview
- Synapse homeserver with a simple SQLite setup (default).
- Optional Element Web for a quick web client.
- Bind mounts in ./synapse and ./element for easy config edits.

Prereqs
- Docker Engine + Compose v2 (docker compose)
- A reverse proxy and TLS (strongly recommended) if exposing to the internet

Quick start
1) Create working dir and copy env template:
   cp .env.example .env
   # Edit .env and set SERVER_NAME to your domain or local value

2) Generate Synapse config (first time only):
   docker compose run --rm synapse generate
   # This creates ./synapse with homeserver.yaml, signing key, etc.

3) Optionally customize Element Web config:
   mkdir -p element
   cat > element/config.json << 'JSON'
   {
     "default_server_config": {
       "m.homeserver": { "base_url": "http://localhost:8008", "server_name": "${SERVER_NAME}" },
       "m.identity_server": { "base_url": "https://vector.im" }
     }
   }
   JSON

4) Start services:
   docker compose up -d

5) Access:
- Element Web: http://localhost:8080
- Synapse client-server API: http://localhost:8008

Notes
- Production DB: For serious deployments, use PostgreSQL and update homeserver.yaml's database section accordingly. You can add a postgres service to docker-compose and set connection credentials, then edit the "database" block in synapse's config.
- Federation: Expose 8448/TCP with valid TLS via your reverse proxy and set SRV/DNS records per Matrix.org docs.
- Registration: homeserver.yaml controls registration (enable/disable, shared secret, etc.).
- Backups: Back up ./synapse (and Postgres data if used) regularly.

Useful commands
- View logs: docker compose logs -f synapse
- Restart: docker compose restart synapse
- Update images: docker compose pull && docker compose up -d
