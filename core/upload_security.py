import os
import subprocess
import tempfile
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from .models import MalwareScanStatus


@dataclass(frozen=True)
class UploadScanResult:
    status: str
    detail: str
    scanned_at: object = None

    @property
    def blocks_upload(self):
        return self.status in {MalwareScanStatus.FAILED, MalwareScanStatus.INFECTED}


def malware_scan_configured():
    return bool(getattr(settings, "MALWARE_SCAN_COMMAND", "").strip())


def scan_uploaded_file(uploaded_file):
    """
    Runs a production-configurable malware scanner for private uploads.
    Local development defaults to NOT_REQUIRED so uploads remain ergonomic.
    Set MALWARE_SCAN_REQUIRED=true and MALWARE_SCAN_COMMAND to block unsafe files.
    The command receives the temporary file path as its final argument.
    """
    required = bool(getattr(settings, "MALWARE_SCAN_REQUIRED", False))
    command = getattr(settings, "MALWARE_SCAN_COMMAND", "").strip()
    timeout = int(getattr(settings, "MALWARE_SCAN_TIMEOUT", 30))

    if not command:
        if required:
            return UploadScanResult(
                MalwareScanStatus.FAILED,
                "Malware scan is required but MALWARE_SCAN_COMMAND is not configured.",
                timezone.now(),
            )
        return UploadScanResult(MalwareScanStatus.NOT_REQUIRED, "Malware scanning is not required for this environment.")

    suffix = os.path.splitext(getattr(uploaded_file, "name", "") or "")[1]
    try:
        position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else None
    except Exception:
        position = None

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_path = tmp.name
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)

    if position is not None:
        try:
            uploaded_file.seek(position)
        except Exception:
            pass

    try:
        completed = subprocess.run(
            [*command.split(), temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return UploadScanResult(MalwareScanStatus.FAILED, "Malware scan timed out.", timezone.now())
    except Exception as exc:
        return UploadScanResult(MalwareScanStatus.FAILED, f"Malware scan failed: {exc}", timezone.now())
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    output = " ".join(part.strip() for part in [completed.stdout, completed.stderr] if part and part.strip())
    detail = output[:240] if output else f"Scanner exit code {completed.returncode}."
    if completed.returncode == 0:
        return UploadScanResult(MalwareScanStatus.CLEAN, detail, timezone.now())
    if completed.returncode == 1:
        return UploadScanResult(MalwareScanStatus.INFECTED, detail, timezone.now())
    return UploadScanResult(MalwareScanStatus.FAILED, detail, timezone.now())


def scan_metadata(result):
    return {
        "malware_scan_status": result.status,
        "malware_scanned_at": result.scanned_at,
        "malware_scan_details": result.detail[:240],
    }
