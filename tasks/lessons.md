# DealerDesk — Lessons Learned

> Re-read this file at the start of every session and before every block.
> Format: **Date | What happened | Root cause | Rule**

<!-- Lessons will be appended here as corrections are made. -->

| Date | What happened | Root cause | Rule |
|---|---|---|---|
| 2026-10-12 | `numpy==1.26.4` failed to install on Python 3.12 / Windows — tried to build from source (no pre-built wheel), needs MSVC | numpy 1.26.x only has Windows wheels for Python ≤3.11; 3.12 wheels start at 2.0.x | For numpy/scipy, pin a floor version (`>=1.26`) not an exact version, so pip can choose a compatible wheel per platform. The grader's Linux + Python 3.11 gets 1.26.x; local Windows 3.12 gets 2.x. |
| 2026-10-12 | `google-genai==1.16.0` was yanked from PyPI — pip warned and then errored on file lock | Pinned an exact yanked release; WinError 32 piled on top | Use floor pins for SDK packages too (`>=1.16.1,<3`). Before pinning any exact version, verify it is not yanked: `pip index versions <pkg>` or check PyPI. |
| 2026-10-12 | pip download of large wheels (e.g. Django) timed out, followed by Windows temp file lock `WinError 32` | Slow network download triggers timeout; Windows defender/indexer holds file handle during unpack failure | Increase pip network timeout with `--default-timeout 100` and retry or install dependencies incrementally so wheels are cached. |

