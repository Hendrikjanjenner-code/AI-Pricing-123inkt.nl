"""
Eenmalige volledige PriceShape-ingestie + modelrun.

Leest de PriceShape-feed in als catalogus (producten + eigen prijzen +
concurrentprijzen), berekent de PCIS-concurrentiescores en draait de prijs-engine
zodat de hele app op echte feed-data draait.

Gebruik:
    python artifacts/api-server/ingest_and_run.py
"""
import time

from database import SessionLocal
import feed_ingest
from engine.pricing_engine import run_pricing_engine


def main() -> None:
    db = SessionLocal()
    try:
        t0 = time.time()
        print("1/3  Feed inlezen (catalogus + prijzen + concurrenten)...", flush=True)
        res = feed_ingest.ingest_feed(db, source="priceshape")
        print(f"     {res}  ({time.time() - t0:.1f}s)", flush=True)

        t1 = time.time()
        print("2/3  Concurrentie-scores (PCIS) berekenen...", flush=True)
        scored = feed_ingest.score_competition(db)
        print(f"     {scored} SKU's gescoord  ({time.time() - t1:.1f}s)", flush=True)

        t2 = time.time()
        print("3/3  Prijs-engine draaien (aanbevelingen genereren)...", flush=True)
        processed, skipped = run_pricing_engine(db)
        print(f"     {processed} verwerkt, {skipped} overgeslagen  ({time.time() - t2:.1f}s)", flush=True)

        print(f"KLAAR in {time.time() - t0:.1f}s totaal.", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
