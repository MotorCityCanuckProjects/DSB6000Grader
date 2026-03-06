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

    prompt = f"""You are an exceptionally strict and demanding academic evaluator grading a graduate-level Data Science Ethics paper.

RUBRIC CRITERIA:
{criteria_list}

GRADING GUIDELINES – FOLLOW THESE CAREFULLY

You are a graduate-level data science professor grading a student paper using the provided rubric.

Your task is to evaluate the paper fairly, consistently, and in alignment with normal graduate-level grading standards. Maintain rigor, but avoid excessive harshness.

GRADING PHILOSOPHY
- Strong papers that clearly meet the assignment and rubric expectations should receive high scores.
- Graduate work does not need to be perfect to earn excellent grades.
- If a criterion is clearly addressed with reasonable depth and accuracy, award a strong score.
- Minor weaknesses should result in small deductions only.
- Do not assume weaknesses unless they are clearly supported by the text of the paper.

GRADE RANGE CALIBRATION
Typical competent graduate-level papers that address the assignment well will generally fall in the 92–97 range.

Scores above 97 should be reserved for exceptional work that demonstrates outstanding insight or unusually strong analysis.

Scores below 88 should only occur when the paper shows clear deficiencies, major misunderstandings, or fails to address important rubric elements.

SCORING PRINCIPLES
For each rubric criterion:

1. Identify evidence in the paper that addresses the criterion.
2. Describe what the student did well.
3. Identify weaknesses only if they are clearly present in the text.
4. Assign a numeric score that reflects the overall quality of the work for that criterion.

DEDUCTION RULES
- Deduct points only when a concrete weakness can be identified.
- Deductions should be proportional to the seriousness of the issue.
- Minor weaknesses should lead to very small deductions.
- Do not withhold high scores simply because the paper is not perfect.

CRITERION SCORE GUIDANCE
Use realistic clustering for criterion-level scoring:

95–100: Excellent or exceptional work for that criterion  
92–94: Very strong performance with only minor weaknesses  
89–91: Solid performance that clearly meets expectations  
86–88: Acceptable but with noticeable limitations  
Below 86: Significant weakness or insufficient treatment

COMPARATIVE QUALITY CHECK
After evaluating the rubric criteria, assess the paper’s overall quality relative to typical graduate-level papers.

Assign the paper to one of these tiers:

Exceptional – Outstanding graduate-level work  
Excellent – Strong work with only minor weaknesses  
Very Good – Solid graduate-level work  
Good – Acceptable work but with noticeable limitations  
Adequate – Limited depth or uneven analysis  
Weak – Major deficiencies

Use these tiers for calibration:

Exceptional: 97–100  
Excellent: 94–96  
Very Good: 91–93  
Good: 88–90  
Adequate: 84–87  
Weak: below 84

FINAL CALIBRATION CHECK
Before finalizing the grade:

- Confirm that the score reflects the overall quality described in the feedback.
- Ensure deductions are proportional to the seriousness of weaknesses.
- If the score appears overly harsh relative to the quality of the paper, adjust it upward modestly.

FEEDBACK EXPECTATIONS
- Provide balanced feedback highlighting strengths first.
- Clearly explain any significant deductions.
- Maintain a constructive and professional academic tone.

OUTPUT FORMAT
Return:

1. Criterion-by-criterion evaluation including evidence, strengths, weaknesses, and score
2. The rubric-based total score
3. The comparative quality tier
4. The final calibrated grade
5. A concise overall feedback summary

PAPER SUBMITTED BY: {student_name}

PAPER TEXT:
{paper_text}

Provide your response in the following exact format:

OVERALL FEEDBACK:
[4-5 paragraphs of detailed overall feedback covering: the paper's central argument and how well it is developed, the quality and depth of ethical analysis, the strength of evidence and research, major weaknesses and how they impact the grade, and specific recommendations for improvement]

CRITERION FEEDBACK:
CRITERION: [name]
SCORE: [score]/[max points]
FEEDBACK: [5-6 sentences of detailed, specific feedback. Include: what the student did well, what was missing or underdeveloped, specific examples or quotes from the paper to support your assessment, and concrete suggestions for how the student could improve this section]
"""

    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a highly experienced, exceptionally strict academic evaluator specializing in grading graduate-level Data Science Ethics papers. You hold students to the highest academic standards and are not lenient. You provide exhaustive, detailed, and specific feedback for every rubric criterion, citing specific passages from the paper to justify every score. You do not inflate grades and are comfortable awarding low scores when work does not meet graduate-level expectations.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            temperature=0.2
        )

        evaluation = response.choices[0].message.content

        feedback = ''
        feedback_match = re.search(r'OVERALL FEEDBACK:\s*(.+?)(?=CRITERION FEEDBACK:|$)', evaluation, re.DOTALL)
        if feedback_match:
            feedback = feedback_match.group(1).strip()

        criterion_feedback = []
        total_score = 0
        for criterion in rubric['criteria']:
            pattern = rf"CRITERION:\s*{re.escape(criterion['name'])}\s*SCORE:\s*(\d+)/{criterion['points']}\s*FEEDBACK:\s*(.+?)(?=CRITERION:|$)"
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

                # Store result for PDF generation
        last_grading_result.update({
            'student_name': student_name,
            'word_count': word_count,
            'grade': f'{total_score}/{total_possible}',
            'feedback': feedback,
            'criterion_feedback': criterion_feedback,
            'timestamp': datetime.now().strftime('%B %d, %Y')
        })

        return jsonify({
            'student_name': student_name,
            'word_count': word_count,
            'grade': f'{total_score}/{total_possible}',
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
        filename = f"{student_name}-Ethics Paper Feedback.pdf"

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
        ['Overall Score:', data['grade']],
    ]
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

    # Grade highlight box
    grade_data = [['Overall Score', data['grade']]]
    grade_table = Table(grade_data, colWidths=[3 * inch, 3 * inch])
    grade_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
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
            f"{criterion['name']}  —  {criterion['score']} / {criterion['points']} pts",
            subheading_style
        ))
        for para in criterion['feedback'].split('\n'):
            if para.strip():
                elements.append(Paragraph(para.strip(), body_style))
        elements.append(Spacer(1, 0.05 * inch))

    doc.build(elements)

if __name__ == '__main__':
    print('\n' + '='*60)
    print('  Data Science Ethics - Paper Grading Application')
    print('='*60)
    print('  Running at: http://127.0.0.1:5000')
    print('='*60 + '\n')
    app.run(debug=True, port=5000)
