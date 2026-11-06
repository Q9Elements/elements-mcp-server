"""Print the host clock's current Coordinated Universal Time (UTC)."""

from datetime import datetime, timezone


def main() -> int:
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
