"""
Backup the app's mutable state (the files that exist ONLY on the persistent
disk: leads, pipeline, contacts, outcomes, auth, logs).

    python3 ops_backup.py            # one snapshot + rotation (+ offsite if configured)

Layers:
  1. Local snapshot  — data/backups/state-<UTC>.tar.gz on the persistent disk,
     rotated (BACKUP_KEEP, default 14). Protects against bad writes/deletes.
  2. Offsite (optional) — the same tarball PUT to any S3-compatible bucket via
     stdlib SigV4 (no boto3). Protects against disk loss. Configure:
         BACKUP_S3_BUCKET     (required to enable)
         BACKUP_S3_REGION     (default us-east-1)
         BACKUP_S3_ENDPOINT   (default s3.<region>.amazonaws.com; set for R2/B2/minio)
         AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

In production docker-entrypoint.sh runs this at boot and then daily. A missing
file is fine (skipped); an empty snapshot is not written.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
BACKUP_DIR = DATA / "backups"

# Mutable state — keep in sync with the .gitignore/.dockerignore mutable lists.
STATE_FILES = [
    "auth_users.csv", "auth_sessions.csv", "auth_otp_codes.csv", ".auth_secret",
    "contact_overrides.csv", "mail_log.csv", "activations.csv", "activity_log.csv",
    "system_owners.csv", "snoozes.csv", "call_claims.csv",
    "growth_employer_pipeline.csv", "growth_university_pipeline.csv",
    "sales_pipeline.csv", "customer_leads.csv", "deal_outcomes.csv",
    "ats_outbox.jsonl", "errors.log",
]
STATE_DIRS = ["customer_invoices"]  # uploaded agency invoices (calculator re-price)


def snapshot() -> Path | None:
    present = [DATA / f for f in STATE_FILES if (DATA / f).exists()]
    present += [DATA / d for d in STATE_DIRS if (DATA / d).is_dir()]
    if not present:
        print("no mutable state present — nothing to back up")
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = BACKUP_DIR / f"state-{stamp}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for p in present:
            tar.add(p, arcname=p.name)
    print(f"snapshot {out.name}: {len(present)} entries, {out.stat().st_size:,} bytes")
    return out


def rotate(keep: int) -> None:
    snaps = sorted(BACKUP_DIR.glob("state-*.tar.gz"))
    for old in snaps[:-keep] if keep > 0 else []:
        old.unlink()
        print(f"rotated out {old.name}")


# ---- offsite: stdlib SigV4 PUT (S3 / R2 / B2 / minio) ----------------------
def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def s3_put(path: Path) -> bool:
    bucket = os.environ.get("BACKUP_S3_BUCKET", "").strip()
    if not bucket:
        return False
    region = os.environ.get("BACKUP_S3_REGION", "us-east-1").strip()
    endpoint = os.environ.get("BACKUP_S3_ENDPOINT", f"s3.{region}.amazonaws.com").strip()
    access = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    if not (access and secret):
        print("BACKUP_S3_BUCKET set but AWS keys missing — skipping offsite")
        return False

    body = path.read_bytes()
    payload_hash = hashlib.sha256(body).hexdigest()
    now = dt.datetime.now(dt.timezone.utc)
    amz_date, date_stamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    host = f"{bucket}.{endpoint}"
    key = f"economist-backups/{path.name}"

    canonical = (f"PUT\n/{key}\n\nhost:{host}\nx-amz-content-sha256:{payload_hash}\n"
                 f"x-amz-date:{amz_date}\n\nhost;x-amz-content-sha256;x-amz-date\n{payload_hash}")
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    to_sign = (f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n"
               f"{hashlib.sha256(canonical.encode()).hexdigest()}")
    k = _sign(_sign(_sign(_sign(("AWS4" + secret).encode(), date_stamp), region), "s3"),
              "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
            f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={sig}")

    req = urllib.request.Request(f"https://{host}/{key}", data=body, method="PUT",
                                 headers={"Host": host, "x-amz-date": amz_date,
                                          "x-amz-content-sha256": payload_hash,
                                          "Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"offsite: PUT s3://{bucket}/{key} → {resp.status}")
            return 200 <= resp.status < 300
    except Exception as e:  # noqa: BLE001 — backup must never crash the host loop
        print(f"offsite upload FAILED: {e}", file=sys.stderr)
        return False


def main() -> int:
    out = snapshot()
    if out is None:
        return 0
    rotate(int(os.environ.get("BACKUP_KEEP", "14")))
    s3_put(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
