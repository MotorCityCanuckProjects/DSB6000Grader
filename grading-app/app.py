from flask import Flask, render_template, request, jsonify, send_file
import yaml
import os
import re
from pathlib import Path
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

APP_DIR = Path(__file__).resolve().parent
PROMPT_CONFIG_PATH = APP_DIR / 'config' / 'grading_prompt.yaml'

def load_rubric():
    with (APP_DIR / 'rubric.yaml').open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_grading_prompts():
    """Load and validate the active grading prompt configuration."""
    try:
        with PROMPT_CONFIG_PATH.open('r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise ValueError(
            f'Grading prompt configuration file is missing: {PROMPT_CONFIG_PATH}'
        ) from exc
    except yaml.YAMLError as exc:
        raise ValueError(
            f'Grading prompt configuration is malformed: {exc}'
        ) from exc
    except OSError as exc:
        raise ValueError(
            f'Grading prompt configuration could not be read: {exc}'
        ) from exc

    if not isinstance(config, dict):
        raise ValueError('Grading prompt configuration must contain a YAML mapping.')

    required_fields = ('system_prompt', 'user_prompt')
    missing_fields = [
        field for field in required_fields
        if not isinstance(config.get(field), str) or not config[field].strip()
    ]
    if missing_fields:
        raise ValueError(
            'Grading prompt configuration is missing required text field(s): '
            + ', '.join(missing_fields)
        )

    required_placeholders = ('{criteria_list}', '{student_name}', '{paper_text}')
    missing_placeholders = [
        placeholder for placeholder in required_placeholders
        if placeholder not in config['user_prompt']
    ]
    if missing_placeholders:
        raise ValueError(
            'Grading user prompt is missing required placeholder(s): '
            + ', '.join(missing_placeholders)
        )

    return config['system_prompt'], config['user_prompt']


def populate_grading_prompt(template, criteria_list, student_name, paper_text):
    """Replace only known placeholders so literal braces in paper text remain unchanged."""
    replacements = {
        '{criteria_list}': criteria_list,
        '{student_name}': student_name,
        '{paper_text}': paper_text,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template

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

    try:
        word_count = len(paper_text.strip().split())
        rubric = load_rubric()
        criteria_list = '\n'.join([
            f"- {c['name']} ({c['points']} points): {c['description']}"
            for c in rubric['criteria']
        ])
        system_prompt, user_prompt_template = load_grading_prompts()
        prompt = populate_grading_prompt(
            user_prompt_template, criteria_list, student_name, paper_text
        )

        messages = [
                {
                    'role': 'system',
                    'content': system_prompt
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ]

        response = client.responses.create(
            model='gpt-6-astra',
            reasoning={'effort': 'medium'},
            input=messages
        )

        evaluation = response.output_text

        # Parse overall feedback
        feedback = ''
        feedback_match = re.search(r'OVERALL FEEDBACK:\s*(.+?)(?=CRITERION FEEDBACK:|$)', evaluation, re.DOTALL)
        if feedback_match:
            feedback = feedback_match.group(1).strip()

        # Parse criterion feedback and calculate rubric total
        criterion_feedback = []
        total_score = 0
        for criterion in rubric['criteria']:
            pattern = rf"CRITERION:\s*{re.escape(criterion['name'])}\s*SCORE:\s*(\d+)/{criterion['points']}\s*FEEDBACK:\s*(.+?)(?=CRITERION:|CALIBRATION NOTES:|FINAL CALIBRATED GRADE:|$)"
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
        filename = f"{student_name}-Ethics Paper Grading Feedback.pdf"

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
    elements.append(Paragraph('DSB6000 Paper Grading Feedback', subtitle_style))
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
