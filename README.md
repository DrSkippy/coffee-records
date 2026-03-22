# Coffee Records

A personal espresso shot tracking application. Log every shot with dose, yield, extraction time, grinder, machine, and prep technique. Attach coffee label photos and shot videos. Visualize trends over time with built-in reports.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask, SQLAlchemy, Pydantic, Gunicorn |
| Frontend | React 19, TypeScript, Vite, Mantine UI |
| Database | PostgreSQL |
| Container | Docker (multi-stage build) |
| Dependency management | Poetry (backend), npm (frontend) |

---

## Building

### Docker (production)

The image is built externally and pushed to the local registry at `localhost:5000`. `docker-compose.yml` pulls from there rather than building in place.

```bash
docker build -t localhost:5000/coffee-records:latest .
docker push localhost:5000/coffee-records:latest
docker compose up -d
```

The multi-stage Dockerfile compiles the React frontend first, then copies the built assets into the Flask static directory. The single container serves both the API and the SPA.

The app listens on port **8181** on the host (`0.0.0.0:8181 → container:5000`).

Coffee label photos are stored on the host at `/var/www/html/resources/coffee/` (mounted into the container at `/resources`), so they persist across container restarts and are accessible to the NGINX static file server.

### NGINX

An NGINX proxy host config is included at `nginx/coffee.drskippy.app`. Drop it into your NGINX Proxy Manager or sites-available directory:

```bash
cp nginx/coffee.drskippy.app /etc/nginx/sites-available/coffee.drskippy.app
ln -s /etc/nginx/sites-available/coffee.drskippy.app /etc/nginx/sites-enabled/
nginx -s reload
```

The config proxies `coffee.drskippy.app` to `127.0.0.1:8181` with a 20 MB upload limit for photo and video uploads.

### Local development

**Backend**

```bash
poetry install
cp .envrc.example .envrc
# edit .envrc with real database credentials, then:
direnv allow          # or: source .envrc

poetry run flask --app "coffee_records:create_app()" run --debug
```

**Frontend**

```bash
cd frontend
npm install
npm run dev           # Vite dev server on :5173, proxies /api to :5000
```

---

## Configuration

### `config.yaml`

```yaml
app:
  debug: false
  secret_key: "changeme"     # change in production

database:
  host: "192.168.1.91"
  port: 5434
  name: "coffee-records"
  pool_size: 5

logging:
  level: "INFO"

server:
  host: "0.0.0.0"
  port: 5000
  workers: 4

uploads:
  coffee_image_dir: "/var/www/html/resources/coffee"
  coffee_image_base_url: "https://resources.drskippy.app/coffee"
```

### Environment variables (`.envrc`)

Required at runtime — never committed to source control:

```bash
export POSTGRES_USER=youruser
export POSTGRES_PASSWORD=yourpassword
```

Optional overrides (used by `docker-compose.yml`):

```bash
export POSTGRES_HOST=192.168.1.91
export POSTGRES_DATABASE=coffee-records
```

---

## Database setup

### First run — create tables

```bash
poetry run python bin/create_tables.py
```

### Migrations

Run these once against an existing database when upgrading:

| Script | Purpose |
|---|---|
| `bin/add_image_column.py` | Adds `coffees.image_filename` |
| `bin/add_video_column.py` | Adds `shots.video_filename` |
| `bin/migrate_maker_to_varchar.py` | Converts `shots.maker` from enum to VARCHAR |

```bash
poetry run python bin/<script>.py
```

All migration scripts are idempotent (`ADD COLUMN IF NOT EXISTS`, `DROP TYPE IF EXISTS`).

---

## Running tests

```bash
poetry run pytest --cov=coffee_records --cov-report=term-missing test/
```

Tests use an in-memory SQLite database — no PostgreSQL required.

---

## UI

The app is a single-page React application served at the root URL. Navigation is via the left sidebar (collapsible on mobile).

### Shots

The default view. Lists the most recent 50 shots, newest first. Each card shows:
- Date and maker
- Coffee name, drink type
- Dose / yield / extraction time
- Grinder and machine labels
- Prep technique badges (Wedge, Shaker, WDT, Flow Taper)
- Notes
- Video link icon (if a video was attached)

Filter the list by maker using the dropdown at the top.

### New Shot

Form to log a shot. All fields except date and maker are optional. The form opens pre-filled with sensible defaults so only changed values need to be entered.

| Field | Default | Notes |
|---|---|---|
| Date | Today | |
| Maker | Scott | Free-text with Scott / Sara as suggestions |
| Coffee | Most recently entered | Searchable select from the coffees list |
| Drink type | americano | americano / latte / cappuccino / drip |
| Grinder | Mazzer (matched by name) | Searchable select |
| Machine | ECM Synchronika (matched by name) | Searchable select |
| Scale | Normcore (matched by name) | Searchable select |
| Pre-infusion time | 5+5 | Free text |
| Dose (g) | 20 | Numeric |
| Final weight (g) | 40 | Numeric |
| Extraction time (s) | 28 | Numeric |
| Grinder temp before (°F) | 64 | Numeric |
| Grinder temp after (°F) | — | Numeric |
| Wedge / Shaker / WDT | ✓ | Checkboxes |
| Flow Taper | — | Checkbox |
| Notes | — | Free text |
| Video | — | Optional video file (mp4, mov, webm, avi, mkv) — uploaded after the shot record is saved |

Equipment defaults (grinder, machine, scale) are resolved by substring match on `make + model` after the equipment list loads, so they adapt automatically if equipment records are renamed.

### Coffees

Manage the catalogue of coffee bags. Each entry stores name, roaster, roast date, roast level, origin country, variety, and process. A coffee label photo can be uploaded directly from the table — a 40×40 thumbnail is shown inline; clicking it opens a centered modal viewer (scales to 90 vw / 600 px max, 80 vh max height) that works on both desktop and mobile. Photos are served from `https://resources.drskippy.app/coffee/<filename>`.

Coffees referenced by shots cannot be deleted (returns a conflict error).

### Equipment

Three tabs — **Grinders**, **Machines**, and **Scales** — each with full create/edit/delete. Equipment referenced by shots cannot be deleted.

**Grinders:** make, model, type (flat / conical / blade), notes.
**Machines:** make, model, type (free text), warmup time (minutes), notes.
**Scales:** make, model, notes.

### Reports

Charts covering a selectable date range (last 7 / 30 / 90 days). All charts can be filtered simultaneously by coffee, grinder, and/or brewing machine.

| Chart | Type | Description |
|---|---|---|
| Shots per Day | Bar | Shot count by date |
| Extraction Time | Line | Extraction seconds per shot over time |
| Dose:Yield Ratio | Line | Output ÷ input ratio per shot |
| Dose vs Yield (g) | Dual line | Dose weight and yield weight per shot |

---

## API

Base URL: `/api`

All endpoints consume and produce `application/json` unless noted.

### Health & version

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok", "database": "ok\|error"}` |
| `GET` | `/api/version` | Returns `{"version": "x.y.z"}` |

### Coffees

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/coffees` | List all coffees (newest roast date first) |
| `POST` | `/api/coffees` | Create a coffee |
| `GET` | `/api/coffees/<id>` | Get one coffee |
| `PUT` | `/api/coffees/<id>` | Update a coffee |
| `DELETE` | `/api/coffees/<id>` | Delete a coffee (409 if shots exist) |
| `POST` | `/api/coffees/<id>/image` | Upload a label photo (`multipart/form-data`, field `file`) |
| `DELETE` | `/api/coffees/<id>/image` | Remove the label photo |

**Coffee object**

```json
{
  "id": 1,
  "name": "Ethiopia Yirgacheffe",
  "roaster": "Blue Bottle",
  "roast_date": "2026-03-01",
  "origin_country": "Ethiopia",
  "roast_level": "light",
  "variety": "Heirloom",
  "process": "washed",
  "image_filename": "a1b2c3d4.jpg",
  "created_at": "2026-03-10T12:00:00Z"
}
```

`roast_level` is one of `light`, `medium`, `dark`, or `null`.

### Shots

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/shots` | List shots (newest first, max 50 by default) |
| `POST` | `/api/shots` | Create a shot |
| `GET` | `/api/shots/<id>` | Get one shot |
| `PUT` | `/api/shots/<id>` | Update a shot |
| `DELETE` | `/api/shots/<id>` | Delete a shot (also removes video from disk) |
| `POST` | `/api/shots/<id>/video` | Upload a video (`multipart/form-data`, field `file`) |
| `DELETE` | `/api/shots/<id>/video` | Remove the video |

**`GET /api/shots` query parameters**

| Parameter | Type | Description |
|---|---|---|
| `maker` | string | Filter by maker name |
| `coffee_id` | integer | Filter by coffee |
| `date_from` | ISO date | Inclusive start date |
| `date_to` | ISO date | Inclusive end date |
| `limit` | integer | Max results (default: all) |
| `offset` | integer | Skip N results |

**Shot object**

```json
{
  "id": 1,
  "date": "2026-03-21",
  "maker": "Scott",
  "coffee_id": 1,
  "coffee_name": "Ethiopia Yirgacheffe",
  "dose_weight": 18.5,
  "pre_infusion_time": "5+5",
  "extraction_time": 28.0,
  "scale_id": 1,
  "scale_label": "Acaia Pearl",
  "final_weight": 37.2,
  "drink_type": "americano",
  "grinder_temp_before": 68.0,
  "grinder_temp_after": 71.5,
  "wedge": false,
  "shaker": true,
  "wdt": true,
  "flow_taper": false,
  "notes": "Dialed in well",
  "video_filename": "e5f6a7b8.mp4",
  "grinder_id": 1,
  "grinder_label": "Niche Zero",
  "device_id": 1,
  "device_label": "Breville Barista Express",
  "created_at": "2026-03-21T09:15:00Z"
}
```

`drink_type` is one of `americano`, `latte`, `cappuccino`, `drip`, or `null`.

### Equipment

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/grinders` | List grinders |
| `POST` | `/api/grinders` | Create a grinder |
| `GET` | `/api/grinders/<id>` | Get one grinder |
| `PUT` | `/api/grinders/<id>` | Update a grinder |
| `DELETE` | `/api/grinders/<id>` | Delete (409 if shots reference it) |
| `GET` | `/api/brewing-devices` | List brewing machines |
| `POST` | `/api/brewing-devices` | Create a machine |
| `GET` | `/api/brewing-devices/<id>` | Get one machine |
| `PUT` | `/api/brewing-devices/<id>` | Update a machine |
| `DELETE` | `/api/brewing-devices/<id>` | Delete (409 if shots reference it) |
| `GET` | `/api/scales` | List scales |
| `POST` | `/api/scales` | Create a scale |
| `GET` | `/api/scales/<id>` | Get one scale |
| `PUT` | `/api/scales/<id>` | Update a scale |
| `DELETE` | `/api/scales/<id>` | Delete (409 if shots reference it) |

### Reports

All report endpoints accept optional query parameters: `date_from`, `date_to` (ISO dates), `coffee_id`, `grinder_id`, `device_id`.

| Method | Path | Response shape |
|---|---|---|
| `GET` | `/api/reports/shots-per-day` | `[{"date": "2026-03-21", "count": 3}]` |
| `GET` | `/api/reports/extraction-trends` | `[{"date": "...", "shot_id": 1, "extraction_time": 28.0}]` |
| `GET` | `/api/reports/dose-yield` | `[{"date": "...", "shot_id": 1, "dose_weight": 18.5, "final_weight": 37.2, "ratio": 2.011}]` |
| `GET` | `/api/reports/by-coffee/<id>` | Aggregate stats + shot list for one coffee |

---

## File uploads

Coffee label photos and shot videos are stored on the host at:

```
/var/www/html/resources/coffee/<uuid>.<ext>
```

And served publicly at:

```
https://resources.drskippy.app/coffee/<uuid>.<ext>
```

Filenames are UUID-based to prevent collisions. Uploading a new file to a record that already has one automatically replaces and deletes the old file. Deleting a shot or removing its video also removes the file from disk.

Accepted formats:
- **Images** (coffee labels): jpg, jpeg, png, webp, gif
- **Videos** (shots): mp4, mov, webm, avi, mkv
