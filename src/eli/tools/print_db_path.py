from pathlib import Path

def main():
    from eli.brain.paths import PATHS
    db = getattr(PATHS, "db_path", None) or getattr(PATHS, "database", None) or getattr(PATHS, "db", None)
    print(str(Path(db)))
