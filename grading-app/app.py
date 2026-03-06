from flask import Flask, render_template, request, jsonify
import yaml
import os
import re
from openai import OpenAI

app = Flask(__name__)

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

GRADING GUIDELINES - FOLLOW THESE STRICTLY:
- You are strict data science professor grading papers at the GRADUATE level. Standards must be exceptionally high.
- Award full points ONLY if the criterion is met with distinction - no gaps, no vagueness, no weaknesses.
- Significantly discount points in sections that are adeqate 
- A score of 95+ should be RARE and reserved for truly outstanding work that exceeds all expectations.
- A score of 80-89 represents high quality work that exceeds the rubric expectations
- A score of 70-79 represents adequate but unremarkable graduate work.
- Scores below 70 should be given whenever the paper shows superficial treatment of topics.
- ALWAYS deduct points for: vague arguments, lack of specific examples, weak evidence, poor citation practices, surface-level analysis, or failure to engage deeply with ethical theory.
- Do NOT give the benefit of the doubt. If something is unclear or underdeveloped, deduct points.
- Be specific about WHY points were deducted for each criterion.

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

        return jsonify({
            'student_name': student_name,
            'word_count': word_count,
            'grade': f'{total_score}/{total_possible}',
            'feedback': feedback,
            'criterion_feedback': criterion_feedback
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print('\n' + '='*60)
    print('  Data Science Ethics - Paper Grading Application')
    print('='*60)
    print('  Running at: http://127.0.0.1:5000')
    print('='*60 + '\n')
    app.run(debug=True, port=5000)
