#!/usr/bin/env python3
"""Eenvoudige USB-sync op basis van mappen.csv.

Werking:
- Script pollt op nieuw aangesloten USB-schijven.
- Voor elke mapping uit mappen.csv vergelijkt het script USB-map met PC-map.
- Bij verschil vraagt het script welke kant geüpdatet moet worden.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


POLL_SECONDS = 2
CSV_FILE = "mappen.csv"


@dataclass
class FolderMapping:
    usb_folder: Path
    pc_folder: Path


def read_mappings(csv_path: Path) -> List[FolderMapping]:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} niet gevonden. Maak een CSV met kolommen: usb_folder,pc_folder"
        )

    mappings: List[FolderMapping] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"usb_folder", "pc_folder"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                "CSV moet kolommen hebben: usb_folder, pc_folder"
            )

        for i, row in enumerate(reader, start=2):
            usb_raw = (row.get("usb_folder") or "").strip()
            pc_raw = (row.get("pc_folder") or "").strip()
            if not usb_raw or not pc_raw:
                print(f"[WAARSCHUWING] Regel {i} overgeslagen (lege waarden).")
                continue

            usb_folder = Path(usb_raw)
            if usb_folder.is_absolute():
                raise ValueError(
                    f"usb_folder op regel {i} moet relatief zijn t.o.v. USB-root: {usb_raw}"
                )

            mappings.append(FolderMapping(usb_folder=usb_folder, pc_folder=Path(pc_raw).expanduser()))

    if not mappings:
        raise ValueError("Geen geldige mappings gevonden in CSV.")

    return mappings


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def folder_manifest(folder: Path) -> Dict[str, Tuple[int, int]]:
    manifest: Dict[str, Tuple[int, int]] = {}
    if not folder.exists():
        return manifest

    for root, dirs, files in os.walk(folder):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not is_hidden((root_path / d).relative_to(folder))]

        for file_name in files:
            full_path = root_path / file_name
            rel_path = full_path.relative_to(folder)
            if is_hidden(rel_path):
                continue
            stat = full_path.stat()
            manifest[str(rel_path).replace("\\", "/")] = (stat.st_size, int(stat.st_mtime_ns))
    return manifest


def sync_status(source: Path, target: Path) -> bool:
    return folder_manifest(source) == folder_manifest(target)


def ensure_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)


def mirror_copy(source: Path, destination: Path) -> None:
    ensure_folder(destination)

    src_manifest = folder_manifest(source)
    dst_manifest = folder_manifest(destination)

    # Kopieer en update bestanden
    for rel_file in src_manifest:
        src_file = source / rel_file
        dst_file = destination / rel_file
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        if rel_file not in dst_manifest or src_manifest[rel_file] != dst_manifest[rel_file]:
            shutil.copy2(src_file, dst_file)
            print(f"  [KOPIE] {src_file} -> {dst_file}")

    # Verwijder bestanden die niet (meer) in source staan
    for rel_file in sorted(set(dst_manifest) - set(src_manifest), reverse=True):
        dst_file = destination / rel_file
        if dst_file.exists():
            dst_file.unlink()
            print(f"  [VERWIJDER] {dst_file}")

    # Ruim lege mappen op
    for root, dirs, _ in os.walk(destination, topdown=False):
        for d in dirs:
            candidate = Path(root) / d
            try:
                candidate.rmdir()
            except OSError:
                pass


def windows_removable_drives() -> Set[Path]:
    import ctypes

    drives: Set[Path] = set()
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    DRIVE_REMOVABLE = 2

    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if bitmask & 1:
            drive = f"{letter}:\\"
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive))
            if drive_type == DRIVE_REMOVABLE:
                drives.add(Path(drive))
        bitmask >>= 1

    return drives


def unix_removable_mounts() -> Set[Path]:
    candidates = [Path("/media"), Path("/run/media"), Path("/Volumes")]
    mounts: Set[Path] = set()
    for base in candidates:
        if not base.exists():
            continue
        for child in base.glob("**/*"):
            if child.is_dir() and any(child.iterdir()):
                mounts.add(child)
    return mounts


def connected_usb_roots() -> Set[Path]:
    if sys.platform.startswith("win"):
        return windows_removable_drives()
    return unix_removable_mounts()


def choose_direction() -> str:
    while True:
        choice = input("Kies update-richting: [u] USB bijwerken vanaf PC, [p] PC bijwerken vanaf USB, [s] overslaan: ").strip().lower()
        if choice in {"u", "p", "s"}:
            return choice
        print("Ongeldige keuze. Typ u, p of s.")


def process_usb(usb_root: Path, mappings: Iterable[FolderMapping]) -> None:
    print(f"\n[INFO] USB gevonden: {usb_root}")

    for mapping in mappings:
        usb_folder = usb_root / mapping.usb_folder
        pc_folder = mapping.pc_folder

        print(f"\nMap-koppeling:\n  USB: {usb_folder}\n  PC:  {pc_folder}")

        ensure_folder(usb_folder)
        ensure_folder(pc_folder)

        if sync_status(usb_folder, pc_folder):
            print("  [OK] Mappen zijn al in sync.")
            continue

        print("  [VERSCHIL] Deze mappen zijn niet in sync.")
        direction = choose_direction()

        if direction == "s":
            print("  [SKIP] Overgeslagen.")
            continue
        if direction == "u":
            print("  [ACTIE] USB map wordt bijgewerkt vanaf PC...")
            mirror_copy(pc_folder, usb_folder)
        elif direction == "p":
            print("  [ACTIE] PC map wordt bijgewerkt vanaf USB...")
            mirror_copy(usb_folder, pc_folder)

        print("  [KLAAR] Sync uitgevoerd.")


def main() -> int:
    csv_path = Path(CSV_FILE)
    try:
        mappings = read_mappings(csv_path)
    except Exception as exc:
        print(f"[FOUT] {exc}")
        return 1

    print("USB-sync gestart. Wacht op USB-insertie...")
    print(f"Gebruik mappings uit: {csv_path.resolve()}")
    print("Stoppen: Ctrl+C")

    previous = connected_usb_roots()

    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = connected_usb_roots()
            new_devices = current - previous

            for usb_root in sorted(new_devices):
                process_usb(usb_root, mappings)

            previous = current
    except KeyboardInterrupt:
        print("\nAfgesloten.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
