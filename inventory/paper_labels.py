"""A4 paper labels: saved box identities, vector QR modules, adjacent pairs."""

import io
from functools import lru_cache
from pathlib import Path

import qrcode
import reportlab
from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MARGIN = 10 * mm
CELL_W = 47.5 * mm
CELL_H = (297 - 20) / 6 * mm
QR_SIZE = 27 * mm


@lru_cache(maxsize=1)
def fonts():
    pdfmetrics.registerFont(
        TTFont("StashLabel", str(settings.BASE_DIR / "static/vendor/label-font.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont(
            "StashLabelBold", str(Path(reportlab.__file__).parent / "fonts/VeraBd.ttf")
        )
    )
    return "StashLabel"


def box_label(box):
    return {
        "code": box.code,
        "title": box.name,
        "url": settings.ORIGIN + "/c/" + box.code,
    }


def qr_matrix(url):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    if QR_SIZE / len(matrix) < 0.4 * mm:
        raise ValueError("The box URL is too long for this compact paper layout")
    return matrix


def fit_text(value, font, size, width, minimum=9):
    value = " ".join(value.split())
    while size > minimum and pdfmetrics.stringWidth(value, font, size) > width:
        size -= 0.5
    if pdfmetrics.stringWidth(value, font, size) > width:
        while value and pdfmetrics.stringWidth(value + "…", font, size) > width:
            value = value[:-1]
        value += "…"
    return value, size


def render_pdf(boxes, title="Stash box labels", sample=False):
    if not boxes:
        raise ValueError("Choose at least one box")
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    pdf.setTitle(title)
    pdf.setAuthor("Stash Conductor")
    font = fonts()
    labels = [box_label(box) for box in boxes]
    matrices = {x["url"]: qr_matrix(x["url"]) for x in labels}
    pages = (len(boxes) + 11) // 12
    for page in range(pages):
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(font, 7)
        heading = (
            "SAMPLE ONLY · Temporary test boxes"
            if sample
            else "Stash Conductor · A4 · Actual size or 100% · Single sided"
        )
        pdf.drawString(MARGIN, A4[1] - 6 * mm, heading)
        pdf.drawRightString(A4[0] - MARGIN, 5 * mm, f"{page + 1} / {pages}")
        for index, label in enumerate(labels[page * 12 : (page + 1) * 12]):
            matrix = matrices[label["url"]]
            for copy in range(2):
                cell = index * 2 + copy
                x = MARGIN + (cell % 4) * CELL_W
                y = A4[1] - MARGIN - (cell // 4 + 1) * CELL_H
                # Boundaries are well outside QR and text clear areas. Empty cells stay empty.
                pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
                pdf.setLineWidth(0.25)
                pdf.rect(x, y, CELL_W, CELL_H, stroke=1, fill=0)
                pdf.setFillColorRGB(0, 0, 0)
                name, size = fit_text(label["title"], font, 14, CELL_W - 6 * mm)
                pdf.setFont(font, size)
                pdf.drawCentredString(x + CELL_W / 2, y + CELL_H - 5 * mm, name)
                code, size = fit_text(
                    label["code"], "StashLabelBold", 10, CELL_W - 6 * mm, 7
                )
                pdf.setFont("StashLabelBold", size)
                pdf.drawCentredString(x + CELL_W / 2, y + CELL_H - 9 * mm, code)
                unit = QR_SIZE / len(matrix)
                left, bottom = x + (CELL_W - QR_SIZE) / 2, y + 7.5 * mm
                path = pdf.beginPath()
                for row, values in enumerate(matrix):
                    for col, dark in enumerate(values):
                        if dark:
                            path.rect(
                                left + col * unit,
                                bottom + (len(matrix) - row - 1) * unit,
                                unit,
                                unit,
                            )
                pdf.drawPath(path, fill=1, stroke=0)
                pdf.setFont(font, 6)
                pdf.drawString(x + 3 * mm, y + 3 * mm, "Stash")
                pdf.drawRightString(x + CELL_W - 3 * mm, y + 3 * mm, "Room __________")
        pdf.showPage()
    pdf.save()
    return output.getvalue()
