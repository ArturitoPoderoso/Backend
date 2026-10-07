from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .services import section_info


def enrollment_pdf(enrollment):
    path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if path.exists() and "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(path)))
    font_normal = "DejaVu" if path.exists() else "Helvetica"
    font_bold = "DejaVu-Bold" if (path.exists() and "DejaVu-Bold" in pdfmetrics.getRegisteredFontNames()) else "Helvetica-Bold"

    out = BytesIO()
    p = canvas.Canvas(out, pagesize=landscape(A4))
    w, h = landscape(A4)

    student = enrollment.student
    period_code = enrollment.period.code
    period_year = period_code[:4] if period_code else "2027"

    p.setTitle(f"Constancia de Matrícula UNFV {period_year}")

    # Logos
    logo_path = Path("frontend/public/fiis-logo.png")
    if not logo_path.exists():
        logo_path = Path("../frontend/public/fiis-logo.png")

    p.setFont(font_bold, 11)
    p.setFillColorRGB(0, 0, 0)
    p.drawCentredString(w / 2.0, h - 35, "FACULTAD DE INGENIERIA INDUSTRIAL Y DE SISTEMAS")
    p.setFont(font_normal, 9.5)
    p.drawCentredString(w / 2.0, h - 50, "OFICINA TECNICA DE SERVICIOS ACADEMICOS")
    
    p.setFont(font_bold, 14)
    p.drawCentredString(w / 2.0, h - 72, f"CONSTANCIA DE MATRICULA  {period_year}")

    if logo_path.exists():
        try:
            p.drawImage(str(logo_path), w - 90, h - 80, width=58, height=58, preserveAspectRatio=True, mask="auto")
            p.drawImage(str(logo_path), 35, h - 80, width=58, height=58, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    # Datos del alumno
    y_meta = h - 105
    p.setFont(font_normal, 9)
    p.drawString(38, y_meta, "Escuela")
    p.drawString(120, y_meta, "INGENIERIA DE SISTEMAS")

    plan_code = "2019" if "2019" in student.plan.name else ("2010" if "2010" in student.plan.name else "2019")
    cycle_num = getattr(student, "official_cycle", 3) or 3
    cycle_str = f"{cycle_num:02d}"

    p.drawString(w - 200, y_meta, "Plan")
    p.setFont(font_bold, 9)
    p.drawString(w - 140, y_meta, plan_code)

    y_meta -= 16
    p.setFont(font_normal, 9)
    p.drawString(38, y_meta, "Especialidad")
    p.drawString(w - 200, y_meta, "Nivel")
    p.setFont(font_bold, 9)
    p.drawString(w - 140, y_meta, cycle_str)

    y_meta -= 16
    p.setFont(font_normal, 9)
    p.drawString(38, y_meta, "Alumno")
    p.setFont(font_bold, 9.5)
    p.drawString(120, y_meta, student.full_name.upper())

    y_meta -= 16
    p.setFont(font_normal, 9)
    conf_date = enrollment.confirmed_at
    date_str = f"{conf_date:%d/%m/%y}" if conf_date else "06/10/26"
    time_str = f"{conf_date:%H:%M:%S}" if conf_date else "13:21:08"
    p.drawString(38, y_meta, f"Fecha         {date_str}                  Hora :  {time_str}")

    p.drawString(w - 240, y_meta, "Cod Alumno")
    p.setFont(font_bold, 13)
    p.setFillColorRGB(0.0, 0.33, 0.95)
    p.drawString(w - 150, y_meta - 1, student.student_code)
    p.setFillColorRGB(0, 0, 0)

    # Tabla de cursos
    y_table = y_meta - 25

    lines = list(
        enrollment.lines.select_related("section", "course")
        .prefetch_related("section__meetings")
        .order_by("course__semester", "course__name")
    )

    table_x = 35
    table_w = w - 70
    row_h = 16

    # Cabecera azul #0080FF
    p.setFillColorRGB(0.0, 0.5, 1.0)
    p.rect(table_x, y_table - row_h, table_w, row_h, fill=1, stroke=0)

    cols = [
        ("Nº", table_x + 8),
        ("Per", table_x + 35),
        ("Código", table_x + 95),
        ("T", table_x + 155),
        ("S", table_x + 185),
        ("Asignaturas", table_x + 220),
        ("Credito", table_x + table_w - 95),
        ("Nivel", table_x + table_w - 45),
    ]

    p.setFillColorRGB(1.0, 1.0, 1.0)
    p.setFont(font_bold, 8.5)
    for title, cx in cols:
        p.drawString(cx, y_table - row_h + 4, title)

    cur_y = y_table - row_h
    p.setFont(font_normal, 8)
    p.setFillColorRGB(0, 0, 0)
    p.setStrokeColorRGB(0.75, 0.75, 0.75)
    p.setLineWidth(0.4)

    total_credits = 0

    for idx, row in enumerate(lines, 1):
        info = row.snapshot or section_info(row.section)
        c_code = (info.get("official_code") or row.course.curricular_code or "101528")[:10]
        c_name = (info.get("course_name") or row.course.name)[:52]
        c_sec_raw = str(info.get("section") or "A")
        c_section = c_sec_raw[-1:] if len(c_sec_raw) > 1 else c_sec_raw
        c_type = "T" if row.course.elective_track is None else "M"
        c_credits = info.get("credits", row.course.credits) or 3
        total_credits += c_credits
        c_level = f"{(row.course.semester or 3):02d}"
        c_per = enrollment.period.code

        cur_y -= row_h

        # Fila con borde
        p.rect(table_x, cur_y, table_w, row_h, fill=0, stroke=1)

        p.drawString(table_x + 8, cur_y + 4, str(idx))
        p.drawString(table_x + 35, cur_y + 4, c_per)
        p.drawString(table_x + 95, cur_y + 4, c_code)
        p.drawString(table_x + 155, cur_y + 4, c_type)
        p.drawString(table_x + 185, cur_y + 4, c_section)
        p.drawString(table_x + 220, cur_y + 4, c_name)
        p.drawString(table_x + table_w - 95, cur_y + 4, f"{c_credits:02d}")
        p.drawString(table_x + table_w - 45, cur_y + 4, c_level)

    # Pie de tabla azul
    cur_y -= row_h
    p.setFillColorRGB(0.0, 0.5, 1.0)
    p.rect(table_x, cur_y, table_w, row_h, fill=1, stroke=0)

    # Recibo box
    p.setFillColorRGB(1.0, 1.0, 1.0)
    p.setFont(font_bold, 8.5)
    p.drawString(table_x + 30, cur_y + 4, "RECIBO:")
    p.rect(table_x + 90, cur_y + 2, 70, row_h - 4, fill=1, stroke=0)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(table_x + 110, cur_y + 4, "0.00")

    # Total de créditos
    p.setFillColorRGB(1.0, 1.0, 1.0)
    p.setFont(font_bold, 8.5)
    p.drawString(table_x + table_w - 190, cur_y + 4, f"TOTAL DE CREDITOS     {total_credits}")

    p.save()
    return out.getvalue()


def teacher_report_pdf(teacher_name, period_code, sections):
    """Reporte privado de carga horaria y alumnos con paginación automática."""
    out = BytesIO()
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if font_path.exists() and "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(font_path)))
    font = "DejaVu" if font_path.exists() else "Helvetica"
    accent = colors.HexColor("#C85219")
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "fiis_title", parent=styles["Title"], fontName=font, fontSize=15, leading=21, textColor=accent
    )
    body = ParagraphStyle("fiis_body", parent=styles["Normal"], fontName=font, fontSize=9, leading=14)
    small = ParagraphStyle("fiis_small", parent=body, fontSize=8, leading=11)
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=44,
        bottomMargin=46,
        title=f"Horarios y alumnos {period_code}",
    )
    story = [
        Paragraph("FIIS · UNFV | HORARIOS Y ALUMNOS", heading),
        Paragraph(f"Docente: {escape(teacher_name)} · Período: {escape(period_code)}", body),
        Spacer(1, 12),
    ]
    if not sections:
        story.append(Paragraph("No tienes secciones asignadas para este período.", body))
    for s in sections:
        info = f"{escape(s['course_name'])} · {escape(s['official_code'] or 'Código pendiente')} · Sección {escape(s['section'])} · Salón {escape(s['classroom'] or 'Por asignar')}"
        hours = ", ".join(f"{m['day_name']} {m['start']}–{m['end']}" for m in s["meetings"]) or "Horario pendiente"
        introduction = [
            Paragraph(info, body),
            Paragraph(f"Horario: {escape(hours)}", small),
            Paragraph(f"Alumnos matriculados: {len(s['students'])}", small),
            Spacer(1, 5),
        ]
        cells = [[Paragraph("Código", small), Paragraph("Alumno matriculado", small)]]
        cells.extend(
            [
                [Paragraph(escape(student["code"]), small), Paragraph(escape(student["name"]), small)]
                for student in s["students"]
            ]
        )
        if not s["students"]:
            cells.append([Paragraph("—", small), Paragraph("Sin matrículas confirmadas", small)])
        table = Table(cells, colWidths=[115, 395], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FCEBDD")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FCF8F4")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#E7DAD0")),
                ]
            )
        )
        story.extend([KeepTogether(introduction), table, Spacer(1, 17)])
    doc.build(story)
    return out.getvalue()
