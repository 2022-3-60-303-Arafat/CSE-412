"""Property Finder Bangladesh (PFB) - development server.

Usage:
    python server.py            start the site at http://127.0.0.1:8765
    python server.py --reset    delete the database and uploads, then load fresh demo data
    python server.py --reset --setup-only    the same, without starting the server (for hosting)

For hosting (PythonAnywhere), wsgi.py is the entry point instead of this file.
"""

import argparse
import os
import shutil
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path

from pfb import db
from pfb.api import router
from pfb.security import LoginThrottle
from pfb.seed import DEMO_PASSWORD, seed
from pfb.web import make_handler

ROOT = Path(__file__).resolve().parent


@dataclass
class Config:
    data_dir: Path = ROOT / "instance"
    public_dir: Path = ROOT / "public"
    # Listing photos are public, so they live under public/. Tests point this at a temporary folder.
    photo_dir: Path = ROOT / "public" / "uploads" / "properties"
    avatar_dir: Path = ROOT / "public" / "uploads" / "avatars"
    # PB-35: there is no SMS gateway, so the one-time code is shown on screen. Set PFB_DEMO_SMS=0 once SMS is connected.
    demo_sms: bool = os.environ.get("PFB_DEMO_SMS", "1") == "1"
    secure_cookies: bool = False
    quiet: bool = False
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)

    @property
    def database(self):
        return self.data_dir / "pfb.sqlite3"

    @property
    def upload_dir(self):
        # Outside public/, so legal papers can only be read through the access-checked API.
        return self.data_dir / "uploads"


def prepare(config, load_demo_data=True):
    """Create the database and upload folder; load demo data into a new database."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.upload_dir.mkdir(exist_ok=True)
    config.photo_dir.mkdir(parents=True, exist_ok=True)
    config.avatar_dir.mkdir(parents=True, exist_ok=True)
    created = db.initialize(config.database)
    if created and load_demo_data:
        connection = db.connect(config.database)
        try:
            seed(connection, config.upload_dir)
            connection.commit()
        finally:
            connection.close()
    return created


def create_server(config, host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), make_handler(router, config))


def main():
    parser = argparse.ArgumentParser(description="Run the Property Finder Bangladesh site.")
    parser.add_argument("--host", default=os.environ.get("PFB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--reset", action="store_true", help="delete all data and load fresh demo data")
    parser.add_argument("--setup-only", action="store_true",
                        help="create (or with --reset, rebuild) the database, then exit without starting the server")
    args = parser.parse_args()

    config = Config(secure_cookies=os.environ.get("PFB_SECURE_COOKIES") == "1")
    if args.reset:
        for path in (config.database, config.database.with_name(config.database.name + "-wal"),
                     config.database.with_name(config.database.name + "-shm")):
            path.unlink(missing_ok=True)
        shutil.rmtree(config.upload_dir, ignore_errors=True)
        # Keep the photo folder itself (and its .gitkeep); remove each listing's photos.
        if config.photo_dir.is_dir():
            for folder in config.photo_dir.iterdir():
                if folder.is_dir():
                    shutil.rmtree(folder, ignore_errors=True)
        if config.avatar_dir.is_dir():
            for picture in config.avatar_dir.iterdir():
                if picture.is_file() and picture.name != ".gitkeep":
                    picture.unlink()
        print("Database, uploads and listing photos deleted.")
    if prepare(config):
        print(f"Created a new database with demo data. Demo password for every account: {DEMO_PASSWORD}")
    if args.setup_only:
        print(f"Database ready at {config.database}")
        return

    server = create_server(config, args.host, args.port)
    print(f"Property Finder Bangladesh is running at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
