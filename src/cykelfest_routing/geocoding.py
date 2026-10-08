"""Background, cached address lookup using Photon's OpenStreetMap data."""

import json
import os
from pathlib import Path
from threading import Event
from time import monotonic

from geopy.exc import GeocoderServiceError
from geopy.geocoders import Photon
from PySide6.QtCore import QThread, Signal


class AddressWorker(QThread):
    progress = Signal(int, int, str)
    results_ready = Signal(object)

    def __init__(self, addresses, cache_path, parent=None, *, geocoder=None, interval=1.1):
        super().__init__(parent)
        self.addresses = addresses
        self.cache_path = Path(cache_path)
        self.geocoder = geocoder
        self.interval = interval
        self.cancelled = Event()

    def cancel(self):
        self.cancelled.set()

    def run(self):
        results, problems = [], []
        cache = {}
        try:
            loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cache = loaded
        except (OSError, ValueError):
            pass
        last_request = -float("inf")
        try:
            geocoder = self.geocoder or Photon(
                user_agent="Cykelfest-Routing/0.1 dinner-safari-planner",
                domain=os.environ.get("CYKELFEST_PHOTON_DOMAIN", "photon.komoot.io"),
                scheme=os.environ.get("CYKELFEST_PHOTON_SCHEME", "https"),
                timeout=10,
            )
            for position, (pid, address) in enumerate(self.addresses, 1):
                if self.cancelled.is_set():
                    break
                self.progress.emit(position - 1, len(self.addresses), address)
                key = f"{getattr(geocoder, 'domain', 'photon')}|{address.strip().casefold()}"
                coordinates = cache.get(key)
                if not (
                    isinstance(coordinates, list)
                    and len(coordinates) == 2
                    and all(isinstance(n, (int, float)) for n in coordinates)
                    and -90 <= coordinates[0] <= 90
                    and -180 <= coordinates[1] <= 180
                ):
                    if self.cancelled.wait(max(0, self.interval - (monotonic() - last_request))):
                        break
                    last_request = monotonic()
                    try:
                        location = geocoder.geocode(address, exactly_one=True)
                    except (GeocoderServiceError, OSError, TimeoutError, ValueError) as error:
                        problems.append(
                            f"{pid}: lookup failed ({error}). Remaining lookups stopped."
                        )
                        break
                    if location is None:
                        problems.append(f"{pid}: no match for {address}")
                        self.progress.emit(position, len(self.addresses), address)
                        continue
                    coordinates = [location.latitude, location.longitude]
                    if not (-90 <= coordinates[0] <= 90 and -180 <= coordinates[1] <= 180):
                        problems.append(f"{pid}: invalid coordinates returned")
                        continue
                    cache[key] = coordinates
                results.append((pid, address, coordinates))
                self.progress.emit(position, len(self.addresses), address)
        except (GeocoderServiceError, OSError, TimeoutError, ValueError, TypeError) as error:
            problems.append(f"Address lookup failed: {error}")
        finally:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(cache), encoding="utf-8")
                temporary.replace(self.cache_path)
            except OSError as error:
                problems.append(f"Could not save the address cache: {error}")
            self.results_ready.emit(
                {"results": results, "problems": problems, "cancelled": self.cancelled.is_set()}
            )
