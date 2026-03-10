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
        "You are a graduate-level data science professor grading a student paper using the provided rubric.\n"
        "Your task is to evaluate the paper fairly, consistently, and in alignment with normal graduate-level grading standards. "
        "Maintain rigor, but avoid excessive harshness.\n\n"

        f"RUBRIC CRITERIA:\n{criteria_list}\n\n"

        "GRADING PHILOSOPHY\n"
        "- Strong papers that clearly meet the assignment and rubric expectations should receive high scores.\n"
        "- Graduate work does not need to be perfect to earn excellent grades.\n"
        "- If a criterion is clearly addressed with reasonable depth and accuracy, award a strong score.\n"
        "- Minor weaknesses should result in small deductions only.\n"
        "- Do not assume weaknesses unless they are clearly supported by the text of the paper.\n\n"

        "GRADE RANGE CALIBRATION\n"
        "Typical competent graduate-level papers that address the assignment well will generally fall in the 84-88 range.\n"
        "Scores above 95 should be reserved for exceptional work that demonstrates outstanding insight or unusually strong analysis.\n"
        "Scores below 82 should occur when the paper shows clear deficiencies, notable misunderstandings, or fails to address important rubric elements.\n\n"

        "SCORING PRINCIPLES\n"
        "For each rubric criterion:\n"
        "1. Identify evidence in the paper that addresses the criterion.\n"
        "2. Describe what the student did well.\n"
        "3. Identify weaknesses only if they are clearly present in the text.\n"
        "4. Assign a numeric score that reflects the overall quality of the work for that criterion.\n\n"

        "NORMATIVE REFERENCE ANCHOR\n"
        "Mentally compare this paper to the typical range of graduate-level data science papers submitted for similar assignments.\n"
        "Use that comparison to judge whether the work is stronger than typical, typical, or weaker than typical before assigning scores.\n"
        "This comparison should guide scoring so that papers of similar quality receive similar grades.\n\n"

        "DEDUCTION RULES\n"
        "- Deduct points only when a concrete weakness can be identified.\n"
        "- Deductions should be proportional to the seriousness of the issue.\n"
        "- Minor weaknesses should lead to small but meaningful deductions.\n"
        "- Do not withhold high scores simply because the paper is not perfect.\n\n"

        "CRITERION SCORE GUIDANCE\n"
        "Use realistic clustering for criterion-level scoring:\n"
        "92-100: Excellent or exceptional work for that criterion\n"
        "85-91: Very strong performance with only minor weaknesses\n"
        "78-84: Solid performance that clearly meets expectations\n"
        "72-77: Acceptable but with noticeable limitations\n"
        "Below 72: Significant weakness or insufficient treatment\n\n"

        "COMPARATIVE QUALITY CHECK\n"
        "First determine whether this paper is ABOVE AVERAGE, TYPICAL, or BELOW AVERAGE compared with graduate-level papers for this assignment.\n"
        "Most papers will fall into the TYPICAL category, but stronger or weaker papers should be clearly distinguished.\n"
        "Use the full grading range when warranted and do not cluster papers into the same score band unless their quality is genuinely similar.\n"
        "Typical papers should often fall in the 84-88 range, but clearly stronger papers should receive higher grades and clearly weaker papers should receive lower grades.\n"
        "After evaluating the rubric criteria, assess the paper's overall quality relative to typical graduate-level papers.\n"
        "Assign the paper to one of these tiers:\n"
        "Exceptional: 94-100 - Outstanding graduate-level work with unusual insight, depth, or sophistication\n"
        "Excellent: 89-93 - Clearly stronger than typical graduate-level work\n"
        "Very Good: 84-88 - Solid graduate-level work that meets expectations well\n"
        "Good: 79-83 - Adequate work with noticeable limitations in depth, clarity, or analysis\n"
        "Adequate: 74-78 - Meaningful weaknesses or uneven treatment of important rubric elements\n"
        "Weak: below 74 - Major deficiencies, serious omissions, or substantial misunderstanding\n\n"

        "FINAL CALIBRATION CHECK\n"
        "Before finalizing the grade:\n"
        "- Confirm that the score reflects the overall quality described in the feedback.\n"
        "- Ensure deductions are proportional to the seriousness of weaknesses.\n"
        "- Avoid grade inflation: typical competent graduate work should generally fall in the mid-to-high 80s.\n"
        "- Also avoid score compression: papers that are meaningfully better or worse than typical should receive meaningfully different grades.\n"
        "- If the score appears overly generous relative to the quality of the paper, adjust it downward modestly.\n"
        "- If the score does not sufficiently distinguish this paper from clearly stronger or weaker work, adjust it accordingly.\n"
        "- Do not default to the same score for many papers; ensure the score reflects the distinct quality of this paper.\n\n"

        "ACADEMIC FEEDBACK STYLE\n"
        "Write feedback as a professor who has carefully read the entire paper.\n"
        "Where possible, quote or paraphrase specific arguments, passages, or examples from the student's paper when explaining strengths or weaknesses.\n"
        "Avoid generic feedback phrases. Comments should clearly reference the student's actual reasoning, claims, evidence, or analysis.\n"
        "Ensure that strengths and weaknesses are directly connected to the student's discussion and ethical analysis.\n\n"

        "FEEDBACK EXPECTATIONS\n"
        "- Provide balanced feedback highlighting strengths first.\n"
        "- Clearly explain any significant deductions.\n"
        "- Maintain a constructive and professional academic tone.\n\n"

        f"PAPER SUBMITTED BY: {student_name}\n\n"
        f"PAPER TEXT:\n{paper_text}\n\n"

        "Provide your response in the following exact format:\n\n"

        "OVERALL FEEDBACK:\n"
        "[4-5 paragraphs of detailed overall feedback covering the paper's central argument, "
        "quality and depth of ethical analysis, strength of evidence and research, "
        "major strengths and weaknesses, and specific recommendations for improvement]\n\n"

        "CRITERION FEEDBACK:\n"
        "CRITERION: [name]\n"
        "SCORE: [score]/[max points]\n"
        "FEEDBACK: [5-6 sentences of detailed specific feedback including what the student did well, "
        "any weaknesses clearly present in the text, specific examples or quotes, "
        "and concrete suggestions for improvement]\n\n"

        "CALIBRATION NOTES:\n"
        "[2-3 sentences explaining the calibration tier assigned, why the final calibrated grade "
        "was adjusted from the raw rubric total, and how the paper compares to typical graduate-level work]\n\n"

        "FINAL CALIBRATED GRADE: [numeric grade out of 100]\n"

    )

    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are an experienced graduate-level data science professor and academic evaluator. '
                        'You grade papers fairly and consistently, holding students to high graduate-level standards '
                        'without being excessively harsh. You provide detailed, balanced, and constructive feedback, '
                        'highlighting strengths as well as areas for improvement. '
                        'You cite specific evidence from the paper to support your evaluations and scores. '
                        'You follow the grading rubric carefully and calibrate your final grade to reflect '
                        'the true quality of the work relative to graduate-level expectations.'
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
