# USBsync

Simpele USB-sync tool in Python.

## Wat doet dit script?

- Leest map-koppelingen uit `mappen.csv`.
- Wacht tot een USB-drive wordt aangesloten.
- Controleert per koppeling of USB-map en PC-map gelijk zijn.
- Vraagt dan welke kant geüpdatet moet worden:
  - `u`: USB bijwerken vanaf PC
  - `p`: PC bijwerken vanaf USB
  - `s`: overslaan

## Vereisten

- Python 3.9+

## `mappen.csv`

Gebruik kolommen:

```csv
usb_folder,pc_folder
Documenten,/home/jij/Documenten
Fotos,/home/jij/Fotos
```

- `usb_folder` moet **relatief** zijn ten opzichte van de root van de USB.
- `pc_folder` mag absoluut pad zijn (of met `~`).

## Starten

```bash
python3 usb_sync.py
```

Het script draait door en detecteert nieuwe USB-apparaten via polling.

## Let op

- Sync is een **mirror** in de gekozen richting: bestanden die niet in de bron staan, worden verwijderd uit het doel.
- Verborgen bestanden/mappen (beginnend met `.`) worden overgeslagen.
