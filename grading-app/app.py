from flask import Flask, render_template, request, jsonify, send_file
import yaml
import os
import math
from pathlib import Path
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from openai import APIError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError
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


class CriterionEvaluation(BaseModel):
    """One rubric criterion returned by the model's structured response."""
    model_config = ConfigDict(extra='forbid')

    criterion_name: str
    score: float
    feedback: str


class GradingEvaluation(BaseModel):
    """Structured grading response requested from the OpenAI Responses API."""
    model_config = ConfigDict(extra='forbid')

    overall_feedback: str
    criteria: list[CriterionEvaluation]

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


def format_score(score):
    """Format whole and fractional rubric scores without unnecessary trailing zeros."""
    if score == 0:
        return '0'
    formatted = format(score.normalize(), 'f')
    return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted


def validate_grading_evaluation(evaluation, rubric):
    """Validate the model response against the authoritative YAML rubric."""
    expected_criteria = {criterion['name']: criterion for criterion in rubric['criteria']}
    expected_names = [criterion['name'] for criterion in rubric['criteria']]
    parsed_names = [criterion.criterion_name for criterion in evaluation.criteria]

    if not evaluation.overall_feedback.strip():
        raise ValueError('Invalid grading response: overall feedback is missing.')

    duplicate_names = sorted({name for name in parsed_names if parsed_names.count(name) > 1})
    if duplicate_names:
        raise ValueError(
            'Invalid grading response: duplicate criterion score(s) for '
            + ', '.join(duplicate_names)
        )

    unexpected_names = sorted(set(parsed_names) - set(expected_criteria))
    if unexpected_names:
        raise ValueError(
            'Invalid grading response: unexpected criterion name(s): '
            + ', '.join(unexpected_names)
        )

    missing_names = [name for name in expected_names if name not in parsed_names]
    if missing_names:
        raise ValueError(
            'Invalid grading response: missing criterion score(s) for '
            + ', '.join(missing_names)
        )

    if len(evaluation.criteria) != len(rubric['criteria']):
        raise ValueError('Invalid grading response: each rubric criterion must appear exactly once.')

    criteria_by_name = {criterion.criterion_name: criterion for criterion in evaluation.criteria}
    criterion_feedback = []
    total_score = Decimal('0')
    total_possible = Decimal('0')
    for name in expected_names:
        criterion = expected_criteria[name]
        response_criterion = criteria_by_name[name]
        if not isinstance(response_criterion.score, (int, float)) or isinstance(response_criterion.score, bool):
            raise ValueError(f'Invalid grading response: nonnumeric score for {name}.')
        if not math.isfinite(response_criterion.score):
            raise ValueError(f'Invalid grading response: nonfinite score for {name}.')
        if not response_criterion.feedback.strip():
            raise ValueError(f'Invalid grading response: feedback is missing for {name}.')

        score = Decimal(str(response_criterion.score))
        criterion_maximum = Decimal(str(criterion['points']))
        if score < 0 or score > criterion_maximum:
            raise ValueError(
                f'Invalid grading response: score for {name} must be between 0 and '
                f'{format_score(criterion_maximum)}.'
            )

        total_score += score
        total_possible += criterion_maximum
        criterion_feedback.append({
            'name': name,
            'points': criterion['points'],
            'score': format_score(score),
            'feedback': response_criterion.feedback.strip(),
        })

    if total_possible <= 0:
        raise ValueError('Rubric total points must be greater than zero.')

    return criterion_feedback, total_score, total_possible


def response_contains_refusal(response):
    """Return whether a Responses API result includes a model refusal."""
    for output_item in getattr(response, 'output', []) or []:
        for content_item in getattr(output_item, 'content', []) or []:
            if getattr(content_item, 'type', None) == 'refusal':
                return True
            if getattr(content_item, 'refusal', None):
                return True
    return False

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

    # A failed replacement submission must not leave an older report available.
    last_grading_result.clear()

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

        response = client.responses.parse(
            model='gpt-6-astra',
            reasoning={'effort': 'medium'},
            input=messages,
            text_format=GradingEvaluation,
        )

        if getattr(response, 'status', 'completed') != 'completed':
            raise ValueError('The grading response was incomplete. Please try again.')

        evaluation = getattr(response, 'output_parsed', None)
        if evaluation is None:
            if response_contains_refusal(response):
                raise ValueError('The grading request was refused. Please revise the submission and try again.')
            raise ValueError('The grading response was incomplete. Please try again.')

        criterion_feedback, total_score, total_possible = validate_grading_evaluation(
            evaluation, rubric
        )
        feedback = evaluation.overall_feedback.strip()

        rubric_total = f'{format_score(total_score)}/{format_score(total_possible)}'
        overall_grade = (total_score / total_possible) * Decimal('100')
        overall_grade_display = f'{format_score(overall_grade)} / 100'

        # Store result for PDF generation
        last_grading_result.update({
            'student_name': student_name,
            'word_count': word_count,
            'rubric_total': rubric_total,
            'overall_grade': overall_grade_display,
            'feedback': feedback,
            'criterion_feedback': criterion_feedback,
            'timestamp': datetime.now().strftime('%B %d, %Y')
        })

        return jsonify({
            'student_name': student_name,
            'word_count': word_count,
            'grade': overall_grade_display,
            'rubric_total': rubric_total,
            'feedback': feedback,
            'criterion_feedback': criterion_feedback
        })

    except APITimeoutError:
        return jsonify({'error': 'The grading request timed out. Please try again.'}), 504
    except APIError:
        return jsonify({'error': 'The grading service could not complete the request. Please try again.'}), 502
    except ValidationError:
        return jsonify({'error': 'The grading response was malformed. Please try again.'}), 422
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 422
    except Exception:
        return jsonify({'error': 'Unable to complete grading. Please try again.'}), 500


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

    # Overall grade is calculated directly from the rubric criterion scores.
    grade_data = [['Overall Grade', data['overall_grade']]]
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

    doc.build(elements)


if __name__ == '__main__':
    print('\n' + '='*60)
    print('  Data Science Ethics - Paper Grading Application')
    print('='*60)
    print('  Running at: http://127.0.0.1:5000')
    print('='*60 + '\n')
    app.run(debug=True, port=5000)
