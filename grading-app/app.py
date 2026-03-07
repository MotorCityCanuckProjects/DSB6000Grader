from flask import Flask, render_template, request, jsonify, send_file
import yaml
import os
import re
from io import BytesIO
from datetime import datetime
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

app = Flask(__name__)

# Store last grading result for PDF generation
last_grading_result = {}

def load_rubric():
    with open('rubric.yaml', 'r') as f:
        return yaml.safe_load(f)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

@app.route('/')
def index():
    rubric = load_rubric()
    return render_template('index.html', rubric=rubric)

@app.route('/api/grade', methods=['POST'])
def grade_paper():
    data = request.get_json()
    student_name = data.get('student_name', 'Unknown Student')
    paper_text = data.get('paper_text', '')

    if not paper_text:
        return jsonify({'error': 'No paper text provided'}), 400

    word_count = len(paper_text.strip().split())
    rubric = load_rubric()

    criteria_list = '\n'.join([
        f"- {c['name']} ({c['points']} points): {c['description']}"
        for c in rubric['criteria']
    ])

    prompt = (
        "You are an exceptionally strict and demanding academic evaluator grading a graduate-level Data Science Ethics paper.\n\n"
        f"RUBRIC CRITERIA:\n{criteria_list}\n\n"
        "GRADING GUIDELINES\n"
        "- Be rigorous and demanding at the graduate level.\n"
        "- Award full points ONLY for exceptional work with no weaknesses.\n"
        "- Deduct points for any deficiencies, gaps, or lack of depth.\n"
        "- A good paper should receive 70-85%; only truly exceptional work deserves 90+.\n"
        "- Cite specific evidence from the paper to justify each score.\n\n"
        "GRADE RANGE CALIBRATION\n"
        "Exceptional: 97-100\n"
        "Excellent: 94-96\n"
        "Very Good: 91-93\n"
        "Good: 88-90\n"
        "Adequate: 84-87\n"
        "Weak: below 84\n\n"
        f"PAPER SUBMITTED BY: {student_name}\n\n"
        f"PAPER TEXT:\n{paper_text}\n\n"
        "Provide your response in the following exact format:\n\n"
        "OVERALL FEEDBACK:\n"
        "[4-5 paragraphs of detailed overall feedback]\n\n"
        "CRITERION FEEDBACK:\n"
        "CRITERION: [name]\n"
        "SCORE: [score]/[max points]\n"
        "FEEDBACK: [5-6 sentences of detailed specific feedback]\n\n"
        "CALIBRATION NOTES:\n"
        "[2-3 sentences explaining the calibration tier assigned, why the final calibrated grade was adjusted from the raw rubric total, and how the paper compares to typical graduate-level work]\n\n"
        "FINAL CALIBRATED GRADE: [numeric grade out of 100]\n"
    )

    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are a highly experienced, exceptionally strict academic evaluator '
                        'specializing in grading graduate-level Data Science Ethics papers. '
                        'You hold students to the highest academic standards and are not lenient. '
                        'You provide exhaustive, detailed, and specific feedback for every rubric criterion, '
                        'citing specific passages from the paper to justify every score. '
                        'You do not inflate grades and are comfortable awarding low scores when '
                        'work does not meet graduate-level expectations.'
                    )
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            temperature=0.2
        )

        evaluation = response.choices[0].message.content

        # Parse overall feedback
        feedback = ''
        feedback_match = re.search(r'OVERALL FEEDBACK:\s*(.+?)(?=CRITERION FEEDBACK:|$)', evaluation, re.DOTALL)
        if feedback_match:
            feedback = feedback_match.group(1).strip()

        # Parse criterion feedback and calculate rubric total
        criterion_feedback = []
        total_score = 0
        for criterion in rubric['criteria']:
            pattern = rf"CRITERION:\s*{re.escape(criterion['name'])}\s*SCORE:\s*(\d+)/{criterion['points']}\s*FEEDBACK:\s*(.+?)(?=CRITERION:|FINAL CALIBRATED GRADE:|$)"
            match = re.search(pattern, evaluation, re.DOTALL | re.IGNORECASE)
            if match:
                score = int(match.group(1))
                crit_feedback = match.group(2).strip()
            else:
                score = round(criterion['points'] * 0.75)
                crit_feedback = 'See overall feedback for details.'

            total_score += score
            criterion_feedback.append({
                'name': criterion['name'],
                'points': criterion['points'],
                'score': score,
                'feedback': crit_feedback
            })

        total_possible = rubric['total_points']
        rubric_total = f'{total_score}/{total_possible}'

        # Parse calibration notes
        calibration_notes = ''
        calibration_match = re.search(r'CALIBRATION NOTES:\s*(.+?)(?=FINAL CALIBRATED GRADE:|$)', evaluation, re.DOTALL | re.IGNORECASE)
        if calibration_match:
            calibration_notes = calibration_match.group(1).strip()

        # Parse the final calibrated grade
        calibrated_grade = None
        calibrated_match = re.search(r'FINAL CALIBRATED GRADE:\s*([\d.]+)', evaluation, re.IGNORECASE)
        if calibrated_match:
            calibrated_grade = calibrated_match.group(1).strip()

        # Store result for PDF generation
        last_grading_result.update({
            'student_name': student_name,
            'word_count': word_count,
            'rubric_total': rubric_total,
            'calibrated_grade': calibrated_grade,
            'calibration_notes': calibration_notes,
            'feedback': feedback,
            'criterion_feedback': criterion_feedback,
            'timestamp': datetime.now().strftime('%B %d, %Y')
        })

        return jsonify({
            'student_name': student_name,
            'word_count': word_count,
            'grade': rubric_total,
            'calibrated_grade': calibrated_grade,
            'calibration_notes': calibration_notes,
            'feedback': feedback,
            'criterion_feedback': criterion_feedback
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-pdf', methods=['GET'])
def download_pdf():
    if not last_grading_result:
        return jsonify({'error': 'No grading result available. Please grade a paper first.'}), 400

    try:
        buffer = BytesIO()
        generate_pdf(buffer, last_grading_result)
        buffer.seek(0)

        student_name = last_grading_result['student_name']
        filename = f"{student_name}-Ethics Paper.pdf"

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_pdf(buffer, data):
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72, leftMargin=72,
        topMargin=72, bottomMargin=72
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor('#1a1a2e'),
        alignment=TA_CENTER,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#0f3460'),
        alignment=TA_CENTER,
        spaceAfter=20,
        fontName='Helvetica'
    )
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#0f3460'),
        spaceBefore=16,
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )
    subheading_style = ParagraphStyle(
        'SubHeading',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#1a1a2e'),
        spaceBefore=10,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['BodyText'],
        fontSize=10,
        leading=15,
        spaceAfter=8,
        fontName='Helvetica'
    )

    elements = []

    # Title
    elements.append(Paragraph('Data Science Ethics', title_style))
    elements.append(Paragraph('Graduate Paper Grading Report', subtitle_style))
    elements.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#0f3460')))
    elements.append(Spacer(1, 0.2 * inch))

    # Student info table
    info_data = [
        ['Student Name:', data['student_name']],
        ['Grading Date:', data['timestamp']],
        ['Word Count:', f"{data['word_count']:,} words"],
        ['Rubric Total:', data['rubric_total']],
    ]
    if data.get('calibrated_grade'):
        info_data.append(['Calibrated Grade:', f"{data['calibrated_grade']} / 100"])
    info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0f3460')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Grade highlight box - use calibrated grade if available, else rubric total
    display_grade = f"{data['calibrated_grade']} / 100" if data.get('calibrated_grade') else data['rubric_total']
    grade_label = 'Final Calibrated Grade' if data.get('calibrated_grade') else 'Rubric Total Score'
    grade_data = [[grade_label, display_grade]]
    grade_table = Table(grade_data, colWidths=[3 * inch, 3 * inch])
    grade_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(grade_table)
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#cccccc')))

    # Overall feedback
    elements.append(Paragraph('Overall Feedback', heading_style))
    for para in data['feedback'].split('\n'):
        if para.strip():
            elements.append(Paragraph(para.strip(), body_style))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#cccccc')))

    # Criterion breakdown
    elements.append(Paragraph('Criterion Breakdown', heading_style))
    for criterion in data['criterion_feedback']:
        elements.append(Paragraph(
            f"{criterion['name']}  -  {criterion['score']} / {criterion['points']} pts",
            subheading_style
        ))
        for para in criterion['feedback'].split('\n'):
            if para.strip():
                elements.append(Paragraph(para.strip(), body_style))
        elements.append(Spacer(1, 0.05 * inch))

    # Calibration notes and final grade at the bottom
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#cccccc')))
    elements.append(Paragraph('Grade Calibration', heading_style))
    if data.get('calibration_notes'):
        for para in data['calibration_notes'].split('\n'):
            if para.strip():
                elements.append(Paragraph(para.strip(), body_style))
    elements.append(Spacer(1, 0.15 * inch))

    # Final calibrated grade box
    if data.get('calibrated_grade'):
        final_data = [['Final Calibrated Grade', f"{data['calibrated_grade']} / 100"]]
        final_table = Table(final_data, colWidths=[3 * inch, 3 * inch])
        final_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0f3460')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 16),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ]))
        elements.append(final_table)

    doc.build(elements)


if __name__ == '__main__':
    print('\n' + '='*60)
    print('  Data Science Ethics - Paper Grading Application')
    print('='*60)
    print('  Running at: http://127.0.0.1:5000')
    print('='*60 + '\n')
    app.run(debug=True, port=5000)
