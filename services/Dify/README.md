# Dify Docker Deployment

This folder contains Docker deployment files for running Dify locally or in the cloud.

## Quick Start

1. Clone this repository and navigate to the `Dify` folder:

   ```pwsh
   cd f:/GitHub/ZZCC/services/Dify
   ```

2. Start Dify with Docker Compose:

   ```pwsh
   docker compose up -d
   ```

   - Dify will be available at http://localhost:8080
   - Data will be stored in the `data` folder (default: SQLite)

3. (Optional) For production, edit `docker-compose.yml` to use Postgres or MySQL.

## Features
- Document ingestion (PDF, DOCX, TXT)
- Entity/relation extraction via LLM workflows
- API integration for custom export

## Integration Steps
1. Upload documents to Dify and extract entities/relations.
2. Export extracted data via API or custom scripts.
3. Transform output to Nebula CSV or import format.
4. Import into NebulaGraph.

## References
- [Dify Documentation](https://docs.dify.ai/)
- [Dify GitHub](https://github.com/langgenius/dify)

---
For advanced workflows, see Dify docs for plugin and API usage.
