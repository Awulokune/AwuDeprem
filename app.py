"""AwuDeprem: AFAD earthquake alerts with a strictly local demo mode."""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from winotify import Notification, audio
except ImportError:
    Notification = None
    audio = None

APP_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "AwuDeprem"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DATA_DIR / "config.json"
SEEN_PATH = APP_DATA_DIR / "seen_events.json"
LOG_PATH = APP_DATA_DIR / "awudeprem.log"
LEGACY_CONFIG_PATH = APP_DIR / "config.json"
CITY_PATH = RESOURCE_DIR / "city_coordinates.json"
API_URL = "https://deprem.afad.gov.tr/apiv2/event/filter"
DEFAULTS = {
    "place_name": "İstanbul", "latitude": 41.0082, "longitude": 28.9784,
    "min_magnitude": 3.5, "max_distance_km": 100.0,
    "sound_enabled": True, "poll_interval_seconds": 30,
}
MAGNITUDE_OPTIONS = tuple(round(i / 10, 1) for i in range(10, 71))
DISTANCE_OPTIONS = (5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500)
EXPECTED_FIELDS = {"eventID", "date", "latitude", "longitude", "depth", "type", "magnitude", "location"}

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    lat, lon = float(latitude), float(longitude)
    if not (math.isfinite(lat) and -90 <= lat <= 90):
        raise ValueError("Enlem -90 ile 90 arasında olmalıdır.")
    if not (math.isfinite(lon) and -180 <= lon <= 180):
        raise ValueError("Boylam -180 ile 180 arasında olmalıdır.")
    return lat, lon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1 = validate_coordinates(lat1, lon1)
    lat2, lon2 = validate_coordinates(lat2, lon2)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_config(path: Path = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULTS)
    if not path.exists() and path == CONFIG_PATH and LEGACY_CONFIG_PATH.exists():
        path = LEGACY_CONFIG_PATH
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    validate_coordinates(cfg["latitude"], cfg["longitude"])
    if not str(cfg["place_name"]).strip():
        raise ValueError("Konum adı boş olamaz.")
    magnitude, distance = float(cfg["min_magnitude"]), float(cfg["max_distance_km"])
    if not math.isfinite(magnitude) or not 1 <= magnitude <= 7:
        raise ValueError("Minimum büyüklük 1.0 ile 7.0 arasında olmalıdır.")
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("Maksimum uzaklık sıfırdan büyük ve sonlu olmalıdır.")
    return cfg


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    validate_coordinates(cfg["latitude"], cfg["longitude"])
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_events(now: datetime | None = None) -> list[dict]:
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(minutes=10)
    params = urllib.parse.urlencode({
        "start": start.strftime("%Y-%m-%dT%H:%M:%S"), "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmag": "0", "limit": "500", "orderby": "timedesc", "format": "json",
    })
    request = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": "AwuDeprem/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return validate_event_payload(payload)


def validate_event_payload(payload) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("AFAD yanıtı beklenen JSON olay listesi biçiminde değil.")
    for item in payload:
        if not isinstance(item, dict) or not EXPECTED_FIELDS.issubset(item):
            raise ValueError("AFAD olay şeması değişmiş veya gerekli alanlar eksik.")
        validate_coordinates(item["latitude"], item["longitude"])
        float(item["magnitude"])
        float(item["depth"])
        if not isinstance(item["date"], str) or not isinstance(item["location"], str) or not isinstance(item["type"], str):
            raise ValueError("AFAD olay alanlarının türü beklenen biçimde değil.")
        if not str(item["eventID"]).strip():
            raise ValueError("AFAD olay kimliği boş.")
    return payload


def eligible_events(events: list[dict], cfg: dict) -> list[tuple[dict, float]]:
    result = []
    for event in events:
        distance = haversine_km(cfg["latitude"], cfg["longitude"], event["latitude"], event["longitude"])
        if float(event["magnitude"]) >= float(cfg["min_magnitude"]) and distance <= float(cfg["max_distance_km"]):
            result.append((event, distance))
    return result


def load_seen(path: Path = SEEN_PATH) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Olay kayıt dosyası geçersiz.")
    return {str(value) for value in data}


SEEN_LOCK = threading.Lock()


def notify_real_event_once(event: dict, distance_km: float, sound_enabled: bool,
                           seen_path: Path = SEEN_PATH) -> bool:
    """Notify and persist a real AFAD ID atomically with respect to this process."""
    event_id = str(event["eventID"])
    with SEEN_LOCK:
        seen = load_seen(seen_path)
        if event_id in seen:
            return False
        title = f"Deprem bildirimi · M{float(event['magnitude']):.1f}"
        body = f"{event['location']} | {distance_km:.1f} km | {event['date']}"
        notify(title, body, sound_enabled)
        seen.add(event_id)
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = seen_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(seen_path)
        return True


def load_cities(path: Path = CITY_PATH) -> dict[str, tuple[float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or len(data) != 81:
        raise ValueError("İl koordinatları dosyası 81 il içermiyor.")
    return {name: validate_coordinates(coords[0], coords[1]) for name, coords in data.items()}


def notify(title: str, body: str, sound_enabled: bool = True) -> None:
    if Notification is None:
        raise RuntimeError("Windows toast için winotify kurulu değil. install.bat dosyasını çalıştırın.")
    toast = Notification(app_id="AwuDeprem", title=title, msg=body)
    if audio is not None:
        toast.set_audio(audio.Default if sound_enabled else audio.Silent, loop=False)
    toast.show()


def demo_notification_content(magnitude: float = 4.2, distance_km: float = 12.0,
                              place: str = "İstanbul açıkları") -> tuple[str, str]:
    """Build a local sample notification; it has no AFAD event ID."""
    if not math.isfinite(float(magnitude)) or float(magnitude) < 0:
        raise ValueError("Demo büyüklüğü geçersiz.")
    if not math.isfinite(float(distance_km)) or float(distance_km) < 0:
        raise ValueError("Demo uzaklığı geçersiz.")
    if not place.strip():
        raise ValueError("Demo yeri boş olamaz.")
    label = "DEMO — gerçek deprem değil"
    return (f"{label} · M{float(magnitude):.1f}",
            f"{label} | {place.strip()} | M{float(magnitude):.1f} | {float(distance_km):g} km — Bu yalnızca yerel test bildirimidir.")


class AwuDepremApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AwuDeprem — Deprem Bildirimleri")
        self.root.minsize(520, 510)
        self.cfg = load_config()
        self.seen = load_seen()
        self.cities = load_cities()
        self.stop_event = threading.Event()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._schedule_poll()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="AwuDeprem", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(main, text="AFAD deprem bildirim ayarları").pack(anchor="w", pady=(0, 12))
        form = ttk.LabelFrame(main, text="Bildirim filtreleri", padding=10)
        form.pack(fill="x")
        self.vars = {key: tk.StringVar(value=str(self.cfg[key])) for key in
                     ("place_name", "latitude", "longitude", "min_magnitude", "max_distance_km")}
        self.vars["max_distance_km"].set(f"{float(self.cfg['max_distance_km']):g}")
        ttk.Label(form, text="Konum adı (il ara)").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.city_combo = ttk.Combobox(form, textvariable=self.vars["place_name"], values=sorted(self.cities), width=26)
        self.city_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.city_combo.bind("<<ComboboxSelected>>", self._city_selected)
        self.city_combo.bind("<KeyRelease>", self._filter_cities)
        ttk.Label(form, text="Minimum büyüklük (M)").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        magnitudes = [f"{value:.1f}" for value in MAGNITUDE_OPTIONS]
        self.magnitude_combo = ttk.Combobox(form, textvariable=self.vars["min_magnitude"], values=magnitudes, state="readonly")
        self.magnitude_combo.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Maksimum uzaklık (km)").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self.distance_combo = ttk.Combobox(form, textvariable=self.vars["max_distance_km"],
                                           values=[str(value) for value in DISTANCE_OPTIONS],
                                           state="readonly")
        self.distance_combo.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Enlem").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        self.latitude_entry = ttk.Entry(form, textvariable=self.vars["latitude"], width=28, state="disabled")
        self.latitude_entry.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Boylam").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        self.longitude_entry = ttk.Entry(form, textvariable=self.vars["longitude"], width=28, state="disabled")
        self.longitude_entry.grid(row=4, column=1, sticky="ew", pady=4)
        self.advanced_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Gelişmiş: koordinatları elle düzenle", variable=self.advanced_var,
                        command=self._toggle_coordinates).grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        form.columnconfigure(1, weight=1)
        self.sound_var = tk.BooleanVar(value=bool(self.cfg["sound_enabled"]))
        ttk.Checkbutton(main, text="Bildirim sesini etkinleştir", variable=self.sound_var).pack(anchor="w", pady=8)
        row = ttk.Frame(main)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Ayarları kaydet", command=self.save_settings).pack(side="left")
        ttk.Button(row, text="Şimdi kontrol et", command=self.poll_once).pack(side="left", padx=8)
        demo = ttk.LabelFrame(main, text="DEMO / test modu — AFAD'a bağlanmaz", padding=10)
        demo.pack(fill="x", pady=(14, 8))
        ttk.Label(demo, text="Yerel örnek: M4.2 • 12 km • İstanbul açıkları").pack(anchor="w")
        ttk.Button(demo, text="Demo bildirimi gönder", command=self.send_demo).pack(anchor="w", pady=(8, 0))
        self.status = tk.StringVar(value="Hazır — AFAD kontrolü arka planda yapılır.")
        ttk.Label(main, textvariable=self.status, wraplength=480).pack(anchor="w", pady=(10, 0))

    def save_settings(self):
        try:
            cfg = {"place_name": self.vars["place_name"].get().strip(),
                   "latitude": float(self.vars["latitude"].get()), "longitude": float(self.vars["longitude"].get()),
                   "min_magnitude": float(self.vars["min_magnitude"].get()),
                   "max_distance_km": float(self.vars["max_distance_km"].get()),
                   "sound_enabled": self.sound_var.get(), "poll_interval_seconds": self.cfg["poll_interval_seconds"]}
            if cfg["place_name"] not in self.cities:
                raise ValueError("Listeden Türkiye'deki 81 ilden birini seçin.")
            if cfg["min_magnitude"] not in MAGNITUDE_OPTIONS:
                raise ValueError("Minimum büyüklüğü listeden seçin (1.0–7.0, 0.1 artışla).")
            if cfg["max_distance_km"] not in DISTANCE_OPTIONS:
                raise ValueError("Maksimum uzaklığı listeden seçin.")
            cfg = load_config_from(cfg)
            save_config(cfg)
            self.cfg = cfg
            self.status.set("Ayarlar config.json dosyasına kaydedildi.")
        except Exception as exc:
            messagebox.showerror("Geçersiz ayar", str(exc))

    def _city_selected(self, _event=None):
        city = self.vars["place_name"].get()
        if city in self.cities:
            self.vars["latitude"].set(f"{self.cities[city][0]:.4f}")
            self.vars["longitude"].set(f"{self.cities[city][1]:.4f}")

    def _filter_cities(self, _event=None):
        query = self.vars["place_name"].get().casefold().strip()
        matches = [name for name in sorted(self.cities) if query in name.casefold()]
        self.city_combo["values"] = matches or sorted(self.cities)

    def _toggle_coordinates(self):
        state = "normal" if self.advanced_var.get() else "disabled"
        self.latitude_entry.configure(state=state)
        self.longitude_entry.configure(state=state)
        if not self.advanced_var.get():
            self._city_selected()

    def send_demo(self):
        # Deliberately does not call fetch_events(), load/save seen IDs, or alter suppression state.
        try:
            title, body = demo_notification_content()
            notify(title, body, self.sound_var.get())
            self.status.set("Demo bildirimi gönderildi. Gerçek olay kayıtları etkilenmedi.")
        except Exception as exc:
            logging.exception("Demo bildirimi gönderilemedi")
            messagebox.showerror("Demo bildirimi gönderilemedi", str(exc))

    def poll_once(self):
        self.status.set("AFAD verileri kontrol ediliyor…")
        threading.Thread(target=self._fetch_and_process, daemon=True).start()

    def _fetch_and_process(self):
        try:
            events = fetch_events()
            for event, distance in eligible_events(events, self.cfg):
                if notify_real_event_once(event, distance, bool(self.cfg["sound_enabled"])):
                    self.seen.add(str(event["eventID"]))
            self.root.after(0, lambda: self.status.set(f"Kontrol tamamlandı · {len(events)} AFAD kaydı incelendi."))
        except Exception as exc:
            logging.exception("AFAD kontrolü başarısız")
            self.root.after(0, lambda message=str(exc): self.status.set(f"Hata kaydedildi: {message}"))

    def _schedule_poll(self):
        if not self.stop_event.is_set():
            self.poll_once()
            self.root.after(max(10, int(self.cfg["poll_interval_seconds"])) * 1000, self._schedule_poll)

    def close(self):
        self.stop_event.set()
        self.root.destroy()


def load_config_from(cfg: dict) -> dict:
    validate_coordinates(cfg["latitude"], cfg["longitude"])
    if not cfg["place_name"].strip():
        raise ValueError("Konum adı boş olamaz.")
    if not math.isfinite(cfg["min_magnitude"]) or cfg["min_magnitude"] < 0:
        raise ValueError("Minimum büyüklük geçerli ve sıfır veya daha büyük olmalıdır.")
    if not math.isfinite(cfg["max_distance_km"]) or cfg["max_distance_km"] <= 0:
        raise ValueError("Maksimum uzaklık sıfırdan büyük olmalıdır.")
    return cfg


def main():
    root = tk.Tk()
    try:
        AwuDepremApp(root)
    except Exception as exc:
        logging.exception("Uygulama başlatılamadı")
        messagebox.showerror("AwuDeprem başlatılamadı", str(exc))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
