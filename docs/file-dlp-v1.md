# File DLP Engine v1 + local OCR

Deployed in original Open WebUI on 8089. Composer button: «Прикрепить файл · DLP + OCR».
Supported: PDF, DOCX, XLSX, UTF-8 TXT, PNG, JPEG, multi-frame TIFF, WebP.
Unsupported/mismatched/corrupt/empty content is not admitted as safe.

## Flow
Authenticated Native raw upload → RAM quarantine in dedicated non-root worker →
format validation/extraction + Tesseract rus+eng → existing Gateway/NLP policy →
signed Vault v2 MASK → encrypted TTL safe representation → owner/chat/policy-bound
attachment ID → existing mandatory Native input/model/output/writer admission.
Original file and filename never enter normal storage, chat or model. No download
of originals is offered. Safe extracted text is inserted into canonical chat;
V2 reveal retains its existing scope/permissions. Attachment processing alone does
not call the model. BLOCK/REVIEW have no context ID. No partial admission.

PDF text layer and full-page raster OCR are both inspected, including mixed pages;
exact normalized duplicate text is removed, divergent OCR candidates both checked.
200 DPI rendering capped before raster allocation. OCR compares original against
EXIF/OSD orientation + grayscale/autocontrast/1.15 contrast/median variant; all
nonidentical candidates are inspected, not just the highest-confidence result.
DOCX XML includes paragraphs/tables/headers/footers/textboxes/comments and media.
XLSX includes hidden sheets, formulas as strings, available cached values,
comments/media; formulas/macros are never run. External relationships, active or
complex unsupported parts cause REVIEW. XML uses defusedxml, ZIP unpack is bounded
and never extracts paths. OCR confidence/boxes/variant and generated block/page
references are retained with the safe context; raw OCR words are ephemeral.

## Limits and isolation
- Upload 10 MiB, 4 attachments; extracted text 6000 chars total per document.
- Combined native turn 7000 chars; existing exact-row history limits still apply.
- PDF/image OCR 20 pages/frames total; 16M pixels per image/page, 100M aggregate.
- ZIP 2000 entries, 40 MB expanded, 12 MB entry, max ratio 200; XLSX 20 sheets,
  20,000 cells. Large files return REVIEW/refusal, not truncation + ALLOW.
- Single-flight OCR, 1 CPU/640 MiB/48 PIDs; read-only root, all caps dropped,
  no-new-privileges; quarantine tmpfs 192 MiB, finally cleanup.
- OCR 18s per variant + 8s OSD, total subprocess deadline 100s; kill process group.
- Extractor loads seccomp deny rules for socket/connect/socketpair; worker has only
  dedicated internal network to Native, no external OCR, HTTP resources disabled.
- Safe contexts encrypted with Fernet using domain-separated admission-key-derived
  key; TTL 15 minutes, expired entries purged on context-store access. No raw text
  in diagnostic logs. SQLite lives in existing webui volume, additive only.
- Policy pinned before extraction and propagated through all file-turn inspections;
  submitting an attachment under another active revision is rejected. Re-upload it.

## Deployment
Append `-f compose.file-dlp.yaml` after existing Native/core/pii/vault-v2 overlays.
Keep existing DLP_AUDITOR_IDS operator setting when recreating webui. Do not remove
volumes. OCR image uses Pillow 13.0.0, PyMuPDF 1.27.2, openpyxl 3.1.5, defusedxml
0.7.1 and locally installed Tesseract rus/eng. No other NLP engine introduced.

## Honest v1 limitations
OCR is not visual understanding or proof of complete text recovery. Blank/low
confidence/error/limit cases return REVIEW; no workflow for approving REVIEW is
added. High-confidence OCR can still omit text. Skew/complex layouts/handwriting
are not guaranteed. Exact duplicates only are removed (not fuzzy duplicates).
Long documents exceeding current Native text/history admission bounds are safely
refused, not silently shortened. No original binary sanitization/redaction or
original retention, no multimodal input. Some uncommon OOXML parts remain
conservatively unsupported. BLOCK/REVIEW currently show verdict and generic reason,
not detailed detected categories because existing Gateway denies before a receipt.
Metadata uses generated block IDs; full spreadsheet cell-level finding mapping and
PII-span-to-OCR-box mapping are not implemented. No cross-request durable job queue:
UI shows combined OCR/DLP processing and final verdict. Pending attachment IDs can
expire; re-upload required. This is a bounded v1, not full OCR completeness proof.
