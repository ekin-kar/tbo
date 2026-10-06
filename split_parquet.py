import os
import pandas as pd

DATA_DIR = "data"
FILES = [
    "BTCUSDT_1m_2020_2026.parquet",
    "ETHUSDT_1m_2020_2026.parquet"
]

for filename in FILES:
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} (not found)")
        continue

    print(f"Reading {filepath}...")
    df = pd.read_parquet(filepath)
    half = len(df) // 2

    base_name = filename.replace(".parquet", "")
    part1_path = os.path.join(DATA_DIR, f"{base_name}_part1.parquet")
    part2_path = os.path.join(DATA_DIR, f"{base_name}_part2.parquet")

    print(f"Writing {part1_path} ({half:,} rows)...")
    df.iloc[:half].to_parquet(part1_path, compression="snappy")

    print(f"Writing {part2_path} ({len(df) - half:,} rows)...")
    df.iloc[half:].to_parquet(part2_path, compression="snappy")

    # Delete original 100MB+ file so Git won't track it
    os.remove(filepath)
    print(f"Deleted original {filepath}\n")

print("All files split and under GitHub's 100MB limit!")