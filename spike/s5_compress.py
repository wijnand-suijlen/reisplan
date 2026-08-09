"""s5: meet de gecomprimeerde grootte van de gemergde rail-only dataset.

Varianten: (a) GTFS-CSV -> zip, (b) GTFS-CSV -> tar.zst (niveau 19),
(c) parquet (zstd) per tabel. Plus NL-shapes apart.
"""

import csv
import io
import tarfile
import time
import zipfile
from pathlib import Path

import duckdb
import zstandard

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "merged" / "merged.duckdb"
EXPORT = ROOT / "data" / "export"
METINGEN = ROOT / "data" / "metingen.csv"

TABELLEN = ["agency", "routes", "trips", "stop_times", "stops", "calendar", "calendar_dates", "clusters", "stop_cluster"]


def meet(metric, waarde):
    with METINGEN.open("a", newline="") as f:
        csv.writer(f).writerow(["s5", "", metric, waarde])
    print(f"{metric}: {waarde}", flush=True)


def main():
    con = duckdb.connect(str(MERGED), read_only=True)
    csv_map = EXPORT / "gtfs"
    pq_map = EXPORT / "parquet"
    csv_map.mkdir(parents=True, exist_ok=True)
    pq_map.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    for t in TABELLEN:
        con.execute(f"COPY {t} TO '{csv_map / (t + '.txt')}' (HEADER, DELIMITER ',')")
        con.execute(f"COPY {t} TO '{pq_map / (t + '.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    csv_bytes = sum(p.stat().st_size for p in csv_map.iterdir())
    meet("csv_onbewerkt_mb", f"{csv_bytes / 1e6:.1f}")

    # (a) zip
    zip_pad = EXPORT / "dataset.zip"
    with zipfile.ZipFile(zip_pad, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in csv_map.iterdir():
            z.write(p, p.name)
    meet("zip_mb", f"{zip_pad.stat().st_size / 1e6:.1f}")

    # (b) tar.zst
    zst_pad = EXPORT / "dataset.tar.zst"
    cctx = zstandard.ZstdCompressor(level=19, threads=-1)
    with zst_pad.open("wb") as f, cctx.stream_writer(f) as w:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for p in csv_map.iterdir():
                tar.add(p, arcname=p.name)
        w.write(buf.getvalue())
    meet("tar_zst_mb", f"{zst_pad.stat().st_size / 1e6:.1f}")

    # (c) parquet+zstd
    pq_bytes = sum(p.stat().st_size for p in pq_map.iterdir())
    meet("parquet_zstd_mb", f"{pq_bytes / 1e6:.1f}")

    # NL-shapes apart
    shapes = ROOT / "data" / "filtered" / "nl" / "shapes.parquet"
    if shapes.exists():
        meet("nl_shapes_parquet_mb", f"{shapes.stat().st_size / 1e6:.1f}")

    meet("duur_s", f"{time.monotonic() - t0:.1f}")


if __name__ == "__main__":
    main()
