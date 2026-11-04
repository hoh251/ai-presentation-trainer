"""Reproducible three-page landscape fixture; ReportLab is an optional authoring tool."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


def build(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(target), pagesize=(960, 540))
    pdf.setTitle("Cat care - integration slides")
    pdf.setAuthor("")
    pdf.setCreator("")
    for lines in [("Quiet corner.", "Hiding place."), ("Clean water.",), ("Tail communication.",)]:
        pdf.setFillColor(HexColor("#102c32"))
        pdf.rect(0, 0, 960, 540, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#71dfb0"))
        pdf.rect(64, 422, 100, 6, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#ffffff"))
        pdf.setFont("Helvetica-Bold", 36)
        for index, line in enumerate(lines):
            pdf.drawString(64, 350 - index * 64, line)
        pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1] / "examples/acceptance/integration-slides.pdf")
