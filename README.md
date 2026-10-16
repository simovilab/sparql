# SPARQL with QLever

Production Docker Compose deployment using the official
[QLever](https://hub.docker.com/r/adfreiburg/qlever) and
[QLever UI](https://hub.docker.com/r/adfreiburg/qlever-ui) images.

- UI: **https://sparql.simovi.org/** (redirects to `/imdb/` initially).
- SPARQL endpoint: **https://sparql.simovi.org/api**.
- Existing Traefik connects through the external **`traefik_proxy`** network.
  Traefik strips `/api` before forwarding requests to QLever on port 7001;
  all other paths go to the UI on port 7000.

## Prerequisites

- A production server with Docker Engine and Docker Compose v2 or newer.
- DNS for `sparql.simovi.org` pointing to that server.
- Traefik already running with its Docker provider, attached to `traefik_proxy`,
  with HTTP/HTTPS entrypoints and a working TLS certificate resolver. The
  defaults are `web`, `websecure`, and `letsencrypt`; change `.env` to match
  your installation. Traefik itself is intentionally not deployed here.
- Start with at least 8 GB RAM for the engine plus memory for the UI, Traefik,
  and the OS, and enough disk for the downloaded RDF, index, and temporary
  indexing files. IMDb grows over time; monitor disk/RAM during indexing.
  Upstream's sample estimates about 5 GB RAM for indexing, not a hard limit.

No container publishes a host port, and no Docker socket is mounted. Both
long-running services are reachable by other containers on `traefik_proxy`;
only attach trusted services to that network.

## First deployment

Run these commands from the repository directory on the production server.

1. Create the local configuration and writable dataset directory:

   ```sh
   cp .env.example .env
   mkdir -p data/imdb secrets
   chmod 700 secrets
   id -u
   id -g
   ```

   Edit `.env`: set `QLEVER_UID` and `QLEVER_GID` to the numeric owner of
   `data/imdb`, and check the Traefik names. The engine and maintenance
   containers run as this user, bypassing the image's interactive/sudo
   entrypoint. Ensure the directory remains writable by that user.

2. Generate the Django secret directly into a private file, without displaying
   it. Do this only once; keep the same key across restarts and backups.

   ```sh
   (umask 077; set -C; openssl rand -hex 32 > secrets/ui_secret_key)
   docker network inspect traefik_proxy
   docker compose config --quiet
   docker compose --profile tools pull
   ```

3. Prepare IMDb explicitly, following the
   [QLever quickstart](https://docs.qlever.dev/quickstart/):

   ```sh
   docker compose run --rm qlever-manage setup-imdb
   docker compose run --rm qlever-manage get-data
   docker compose run --rm qlever-manage index
   ```

   `setup-imdb` runs **`qlever setup-config imdb`** and refuses to replace an
   existing `Qleverfile`. Downloading and indexing can take several minutes
   and require internet access and substantial disk space. They are never
   run automatically on server startup. The CLI uses `--system native` for
   indexing inside the container, so no nested Docker or host CLI is needed.

4. Start the services:

   ```sh
   docker compose up -d --wait --wait-timeout 300
   docker compose ps
   docker compose logs --tail 100 qlever qlever-ui
   ```

   The engine must become healthy before the UI starts. On first boot, Docker
   seeds the UI volume with the image's bundled SQLite database. Initialization
   runs migrations, disables **all bundled accounts** and existing sessions,
   and selects the IMDb backend with the public HTTPS `/api` URL. Subsequent
   restarts preserve administrator accounts you create yourself.

5. Verify a query through Traefik:

   ```sh
   curl --fail --get 'https://sparql.simovi.org/api' \
     --header 'Accept: application/sparql-results+json' \
     --data-urlencode 'query=SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5'
   ```

   Open `https://sparql.simovi.org/` and run an IMDb example query. If certificates
   or routing fail, check the DNS, Traefik resolver/entrypoint names and logs,
   and network membership; the local smoke test does not validate external DNS
   or TLS.

## Production behavior

- Images are pinned to immutable multi-platform digests in `compose.yaml` and
  `.env.example`. Upgrade deliberately: index formats can change, so back up
  first and rebuild with the same engine image used for serving when required.
- Query memory, cache size, concurrency, and default timeout are configurable
  in `.env`. The container memory limit also covers index metadata and other
  overhead; a query-memory setting alone is not a total RAM limit.
- The server reads the dataset `NAME` and `TEXT_INDEX` from the active
  `Qleverfile`. Serving settings come from `.env`, not the Qleverfile's server
  section. Both text-indexed IMDb and non-text-indexed custom datasets work.
- No engine access token is configured: privileged API operations, including
  SPARQL updates, are disabled. In particular, the sample Qleverfile's
  predictable `ACCESS_TOKEN = imdb` is **not** used.
- Public queries are unauthenticated. Outbound SPARQL `SERVICE` requests are
  disabled to prevent access to internal services. IMDb examples that join
  Wikidata will therefore fail intentionally. If needed, set
  `QLEVER_SERVICE_ALLOW_PREFIX=https://qlever.dev/api/wikidata` to allow only
  that trusted endpoint, then recreate the engine.
- Django debug mode is off; the key is read from a Compose secret file, hosts
  and CSRF origins are restricted, and secure cookies and trusted proxy HTTPS
  handling are enabled. Keep Traefik's forwarded-header trust restricted.
- A small static-storage compatibility override removes leading slashes from
  asset names used by the pinned UI's formatter template, preserving hashed
  WhiteNoise assets without enabling debug mode.
- For a high-traffic public deployment, add appropriate request/rate limits
  in your existing Traefik configuration and monitor resource consumption.
- Docker logs are rotated. Restart policies cover process exits; an unhealthy
  container is not automatically restarted by Compose.

Create a private administrator if you need to configure UI backends/examples:

```sh
docker compose exec qlever-ui python manage.py createsuperuser
```

Use `/admin/` to log in. The bundled `demo` credentials do not work.
The selected backend and public endpoint are reapplied on startup; manage
those through `.env`. Other backend display settings and queries persist.

## Replace IMDb with your own RDF

Use a **separate dataset directory**, keeping the IMDb files as a rollback
option. Bulk upload here means copying RDF files to the server and rebuilding
an index; a public upload interface is intentionally not provided.

1. Stop both services before changing the active dataset:

   ```sh
   docker compose stop qlever-ui qlever
   mkdir -p data/custom
   ```

2. Copy your RDF to `data/custom/dataset.ttl` and create
   `data/custom/Qleverfile` with:

   ```ini
   [data]
   NAME = custom
   DESCRIPTION = My RDF dataset
   FORMAT = ttl

   [index]
   INPUT_FILES = dataset.ttl
   CAT_INPUT_FILES = cat ${INPUT_FILES}
   PARALLEL_PARSING = false
   TEXT_INDEX = none

   [runtime]
   SYSTEM = native
   ```

   Set `FORMAT = nt` or `nq` for N-Triples or N-Quads as appropriate, and adjust
   the input filename. Sequential Turtle parsing is safe even when prefixes
   occur throughout the file. For larger/multiple/compressed files, consult the
   [Qleverfile reference](https://docs.qlever.dev/qleverfile/). Use a literal
   `NAME` without slashes. Set `TEXT_INDEX = from_literals` before indexing if
   you want full-text search.

3. Change `QLEVER_DATA_DIR=./data/custom` in `.env`, ensure ownership matches
   `QLEVER_UID`/`QLEVER_GID`, and build:

   ```sh
   docker compose run --rm qlever-manage index
   ```

   Do **not** run `get-data` for files you uploaded yourself. Indexing refuses
   to replace an existing index unless you explicitly pass
   `index --overwrite-existing`; never do that while the engine is running.

4. The IMDb UI configuration contains IMDb-specific prefixes and autocomplete
   queries. Before offering the new dataset publicly, create/configure a
   backend for it in the UI admin and set `QLEVER_UI_BACKEND` to its slug.
   For initial configuration, leave `QLEVER_UI_BACKEND=imdb`, start the services,
   create an administrator if necessary, and edit/create the backend in
   `/admin/`. The old IMDb presets will not fit your data. If staging the UI
   publicly is unsuitable, configure it behind a temporary Traefik access
   restriction. Then select the new slug and recreate the services:

   ```sh
   docker compose up -d --wait --wait-timeout 300
   ```

   The URL stays `/api`; the UI initialization selects your configured backend.
   Repeat the verification query against your own data.

## Backups and operations

- Back up `.env`, `secrets/ui_secret_key`, the active dataset directory
  (including `Qleverfile`, source RDF, and **all** generated index files), and
  the `sparql_qlever_ui_db` Docker volume.
- Stop the UI before taking a filesystem copy of SQLite; preserve its
  `.production-initialized` marker too. Do not take an index backup during
  indexing. Restore the database volume and key together.
- `docker compose down` preserves the named UI volume and bind-mounted RDF.
  **Do not use `docker compose down -v`** unless you intend to delete the UI
  database, accounts, and configuration.
- To roll back a dataset, stop both services, restore its directory/image
  reference and backend slug in `.env`, then run `docker compose up -d --wait`.

## Local validation

```sh
docker compose config --quiet
python3 tests/smoke.py
```

The smoke test uses the pinned images, an isolated temporary Compose project,
network, UI volume, secret, and a tiny synthetic RDF dataset. It exercises
`setup-config imdb` without downloading IMDb, builds and queries a real text
index, checks UI health/configuration and account hardening, and cleans up its
test containers and volume. It also verifies formatter assets, API restrictions,
administrator persistence, and switching to a non-text custom index.
It does not attach to `traefik_proxy`, publish any
ports, or test your production Traefik, DNS, or certificates.
