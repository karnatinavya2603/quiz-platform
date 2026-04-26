from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4


def generate_result_pdf(username, mcq_score, mcq_total, coding_score, all_results):
    path   = f"/tmp/result_{username}.pdf"
    doc    = SimpleDocTemplate(path, pagesize=A4,
                                rightMargin=40, leftMargin=40,
                                topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    story.append(Paragraph("Quiz Platform — Result Report", ParagraphStyle(
        'Title', parent=styles['Title'], fontSize=20,
        textColor=colors.HexColor('#1e2a3a'), spaceAfter=6)))
    story.append(Paragraph(f"Candidate: <b>{username}</b>", styles['Normal']))
    story.append(Paragraph(
        f"Date: {datetime.now().strftime('%d %B %Y  %I:%M %p')}", styles['Normal']))
    story.append(Spacer(1, 16))

    # Score summary
    total   = mcq_score + coding_score
    summary = [
        ['Section', 'Score'],
        ['MCQ',    f"{mcq_score} / {mcq_total}"],
        ['Coding', f"{coding_score}"],
        ['Total Score', f"{total}"],
    ]
    t = Table(summary, colWidths=[280, 160])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#1e2a3a')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1,-1), 11),
        ('BACKGROUND',    (0, 3), (-1, 3), colors.HexColor('#28a745')),
        ('TEXTCOLOR',     (0, 3), (-1, 3), colors.white),
        ('FONTNAME',      (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('GRID',          (0, 0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS',(0, 1), (-1, 2),
         [colors.HexColor('#f8f9fa'), colors.white]),
        ('PADDING',       (0, 0), (-1,-1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Coding test case details
    if all_results:
        story.append(Paragraph("Coding Test Case Results", ParagraphStyle(
            'H2', parent=styles['Heading2'], fontSize=13,
            textColor=colors.HexColor('#1e2a3a'), spaceAfter=6)))

        for i, item in enumerate(all_results, 1):
            story.append(Paragraph(f"Q{i}: {item['question']}", styles['Heading3']))
            rows = [['Input', 'Expected', 'Got', 'Result']]
            for r in item['results']:
                rows.append([r['input'], r['expected'], r['output'], r['status']])

            ct = Table(rows, colWidths=[110, 110, 110, 80])
            ct.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#343a40')),
                ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
                ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0, 0), (-1,-1), 9),
                ('GRID',       (0, 0), (-1,-1), 0.4, colors.grey),
                ('PADDING',    (0, 0), (-1,-1), 6),
                *[('BACKGROUND', (3, ri), (3, ri),
                   colors.HexColor('#d4edda') if rows[ri][3] == 'PASS'
                   else colors.HexColor('#f8d7da'))
                  for ri in range(1, len(rows))]
            ]))
            story.append(ct)
            story.append(Spacer(1, 10))

    doc.build(story)
    return path
