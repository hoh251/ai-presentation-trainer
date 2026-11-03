from io import BytesIO

from pypdf import PdfReader

from .errors import APIError


def extract_pages(content: bytes):
    if not content.startswith(b"%PDF-"):
        raise APIError(422, "PDF_INVALID", "ไฟล์ไม่ใช่ PDF ที่อ่านได้")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise APIError(422, "PDF_ENCRYPTED", "กรุณาใช้ PDF ที่ไม่มีรหัสผ่าน")
        if not 1 <= len(reader.pages) <= 10:
            raise APIError(422, "PDF_PAGE_LIMIT", "รองรับ PDF 1–10 หน้า")
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
    except APIError:
        raise
    except Exception as exc:
        raise APIError(422, "PDF_INVALID", "อ่าน PDF ไม่สำเร็จ") from exc
    if not any(p.strip() for p in pages):
        raise APIError(422, "PDF_NO_TEXT", "PDF ไม่มีข้อความที่ดึงได้ กรุณาใช้ไฟล์ที่มีข้อความ")
    return pages
