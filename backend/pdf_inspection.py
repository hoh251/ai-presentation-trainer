"""Offline page diagnostics, not an OCR engine or a calibrated slide classifier.

This module does not change upload acceptance or put visual descriptions into
contract-v1 text evidence. Coordinates from pypdf visitors remain unverified.
"""
from io import BytesIO
from statistics import median

from pypdf import PdfReader

from .errors import APIError


def inspect_pdf(content):
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise APIError(422, "PDF_ENCRYPTED", "กรุณาใช้ PDF ที่ไม่มีรหัสผ่าน")
        pages = []
        for number, page in enumerate(reader.pages, 1):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            blocks = []
            def visitor(text, cm, tm, font, size):
                if text.strip():
                    blocks.append(dict(text=text, x=float(tm[4]), y=float(tm[5]), font_size=float(size), coordinates_verified=False))
            text = page.extract_text(visitor_text=visitor) or ""
            compact = "".join(text.split())
            suspicious = sum(c == '\ufffd' or '\ue000' <= c <= '\uf8ff' for c in compact)
            resources = page.get("/Resources")
            resources = resources.get_object() if resources else {}
            objects = resources.get("/XObject")
            images = sum(obj.get_object().get("/Subtype") == "/Image" for obj in objects.get_object().values()) if objects else 0
            fonts = [b["font_size"] / height for b in blocks if b["font_size"] > 0 and height > 0]
            big_font = median(fonts) >= .022 if fonts else False
            long_lines = sum(len(line.strip()) > 180 for line in text.splitlines())
            if not compact:
                status = "uncertain"
            elif width / max(height, 1) >= 1.18 and big_font and len(compact) <= 2000:
                status = "slide"
            elif len(compact) >= 1800 and not big_font and (long_lines or width < height):
                status = "document"
            else:
                status = "uncertain"
            pages.append(dict(page=number, width=width, height=height, slide_status=status, text=text,
                              blocks=blocks, text_characters=len(compact), suspicious_glyphs=suspicious,
                              image_count=images, needs_visual_review=bool(suspicious or not compact or objects),
                              visual_status="not_processed", usable_for_visual_questions=False))
    except APIError:
        raise
    except Exception as exc:
        raise APIError(422, "PDF_INVALID", "อ่าน PDF ไม่สำเร็จ") from exc
    votes = [p["slide_status"] for p in pages]
    status = "slide" if votes and votes.count("slide") / len(votes) >= .65 else "document" if votes and votes.count("document") / len(votes) >= .65 else "uncertain"
    return dict(classifier="uncalibrated-layout-heuristic", detection_metrics_available=False,
                classification=status, page_count=len(pages), contract_v1_page_limit=10,
                contract_v1_page_count_supported=1 <= len(pages) <= 10, ocr_performed=False, pages=pages)
