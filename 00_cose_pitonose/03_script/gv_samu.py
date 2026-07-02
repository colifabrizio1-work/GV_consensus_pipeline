from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Iterable

OFFICIAL_SAMU_DIR = Path(r"\\luxnt\Retail\AAA_Retail\zzzz_Coli\Script\03 - py\00 - utilities")
SELF_EMAIL = "fabrizio.coli@luxottica.com"

if str(OFFICIAL_SAMU_DIR) not in sys.path:
    sys.path.insert(0, str(OFFICIAL_SAMU_DIR))

from samu import build_html_body, send_mail  # noqa: E402


def send_update_status(
    *,
    pipeline_name: str,
    status: str,
    lines: Iterable[str],
    log_path: str | Path | None = None,
    error: BaseException | None = None,
    active: bool = True,
) -> None:
    if not active:
        return

    status_clean = status.upper().strip()
    subject = f"S.A.M. - GV {pipeline_name} Update {status_clean}"
    body_lines = list(lines)
    if error is not None:
        body_lines.extend([
            "",
            "Errore:",
            f"{type(error).__name__}: {error}",
            "",
            "Traceback:",
            traceback.format_exc(),
        ])

    attachments = []
    if log_path:
        path = Path(log_path)
        if path.exists():
            attachments.append(path)

    send_mail(
        mail_recipients=[SELF_EMAIL],
        subject=subject,
        text="\n".join(str(line) for line in body_lines),
        html_body=build_html_body("\n".join(str(line) for line in body_lines)),
        attachments=attachments,
    )
