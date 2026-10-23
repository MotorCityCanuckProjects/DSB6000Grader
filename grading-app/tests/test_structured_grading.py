import os
import sys
import unittest
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault('OPENAI_API_KEY', 'test-key')
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import app  # noqa: E402


class StructuredGradingTests(unittest.TestCase):
    def setUp(self):
        self.original_client = app.client
        app.last_grading_result.clear()
        self.rubric = {
            'total_points': 40,
            'criteria': [
                {'name': 'Criterion A', 'points': 10},
                {'name': 'Criterion B', 'points': 30},
            ],
        }

    def tearDown(self):
        app.client = self.original_client
        app.last_grading_result.clear()

    def evaluation(self, criteria=None, overall_feedback='Substantive overall feedback.'):
        return app.GradingEvaluation(
            overall_feedback=overall_feedback,
            criteria=criteria or [
                app.CriterionEvaluation(
                    criterion_name='Criterion A', score=7.5,
                    feedback='Specific evidence-based feedback.',
                ),
                app.CriterionEvaluation(
                    criterion_name='Criterion B', score=12.5,
                    feedback='Specific evidence-based feedback.',
                ),
            ],
        )

    def assert_invalid(self, evaluation, expected_message):
        with self.assertRaisesRegex(ValueError, expected_message):
            app.validate_grading_evaluation(evaluation, self.rubric)

    def test_valid_response_and_normalization(self):
        feedback, total, possible = app.validate_grading_evaluation(
            self.evaluation(), self.rubric
        )
        self.assertEqual(total, Decimal('20.0'))
        self.assertEqual(possible, Decimal('40'))
        self.assertEqual(app.format_score((total / possible) * 100), '50')
        self.assertEqual(feedback[0]['score'], '7.5')

    def test_100_point_rubric_calculation(self):
        rubric = {
            'total_points': 100,
            'criteria': [
                {'name': 'Criterion A', 'points': 40},
                {'name': 'Criterion B', 'points': 60},
            ],
        }
        evaluation = self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=40, feedback='Feedback.'),
            app.CriterionEvaluation(criterion_name='Criterion B', score=60, feedback='Feedback.'),
        ])
        _, total, possible = app.validate_grading_evaluation(evaluation, rubric)
        self.assertEqual(total, Decimal('100'))
        self.assertEqual(possible, Decimal('100'))
        self.assertEqual(app.format_score((total / possible) * 100), '100')

    def test_missing_duplicate_and_unknown_criteria_are_rejected(self):
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=5, feedback='Feedback.'),
        ]), 'missing criterion')
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=5, feedback='Feedback.'),
            app.CriterionEvaluation(criterion_name='Criterion A', score=5, feedback='Feedback.'),
        ]), 'duplicate criterion')
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=5, feedback='Feedback.'),
            app.CriterionEvaluation(criterion_name='Unknown', score=5, feedback='Feedback.'),
        ]), 'unexpected criterion')

    def test_invalid_scores_are_rejected(self):
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=-1, feedback='Feedback.'),
            app.CriterionEvaluation(criterion_name='Criterion B', score=5, feedback='Feedback.'),
        ]), 'between 0 and 10')
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=11, feedback='Feedback.'),
            app.CriterionEvaluation(criterion_name='Criterion B', score=5, feedback='Feedback.'),
        ]), 'between 0 and 10')
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation.model_construct(
                criterion_name='Criterion A', score='not-a-number', feedback='Feedback.'
            ),
            app.CriterionEvaluation(criterion_name='Criterion B', score=5, feedback='Feedback.'),
        ]), 'nonnumeric score')
        self.assert_invalid(self.evaluation([
            app.CriterionEvaluation(criterion_name='Criterion A', score=float('nan'), feedback='Feedback.'),
            app.CriterionEvaluation(criterion_name='Criterion B', score=5, feedback='Feedback.'),
        ]), 'nonfinite score')

    def test_incomplete_and_refused_responses_do_not_generate_grades(self):
        app.last_grading_result.update({'overall_grade': '100 / 100'})
        app.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(return_value=SimpleNamespace(
            status='completed', output_parsed=None, output=[]
        ))))
        response = app.app.test_client().post('/api/grade', json={
            'student_name': 'Ada', 'paper_text': 'Paper text'
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn('incomplete', response.get_json()['error'])
        self.assertEqual(app.app.test_client().get('/api/download-pdf').status_code, 400)

        with self.assertRaises(app.ValidationError) as malformed:
            app.GradingEvaluation.model_validate({
                'overall_feedback': 'Feedback.', 'criteria': 'not an array'
            })
        app.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(
            side_effect=malformed.exception
        )))
        response = app.app.test_client().post('/api/grade', json={
            'student_name': 'Ada', 'paper_text': 'Paper text'
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn('malformed', response.get_json()['error'])

        refusal = SimpleNamespace(type='refusal', refusal='Cannot comply')
        app.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(return_value=SimpleNamespace(
            status='completed', output_parsed=None,
            output=[SimpleNamespace(content=[refusal])],
        ))))
        response = app.app.test_client().post('/api/grade', json={
            'student_name': 'Ada', 'paper_text': 'Paper text'
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn('refused', response.get_json()['error'])

    def test_timeout_and_api_error_are_safe(self):
        request = SimpleNamespace(url='https://api.openai.com/v1/responses')
        app.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(
            side_effect=app.APITimeoutError(request=request)
        )))
        response = app.app.test_client().post('/api/grade', json={
            'student_name': 'Ada', 'paper_text': 'Paper text'
        })
        self.assertEqual(response.status_code, 504)
        self.assertIn('timed out', response.get_json()['error'])

        app.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(
            side_effect=app.APIError('service failure', request=request, body=None)
        )))
        response = app.app.test_client().post('/api/grade', json={
            'student_name': 'Ada', 'paper_text': 'Paper text'
        })
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('service failure', response.get_json()['error'])

    def test_api_request_uses_structured_output_and_pdf_uses_calculated_grade(self):
        rubric = app.load_rubric()
        evaluation = app.GradingEvaluation(
            overall_feedback='Substantive overall feedback.',
            criteria=[
                app.CriterionEvaluation(
                    criterion_name=criterion['name'], score=criterion['points'],
                    feedback='Specific evidence-based feedback.',
                )
                for criterion in rubric['criteria']
            ],
        )
        parse = Mock(return_value=SimpleNamespace(
            status='completed', output_parsed=evaluation, output=[]
        ))
        app.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

        response = app.app.test_client().post('/api/grade', json={
            'student_name': 'Ada', 'paper_text': 'Paper text'
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data['grade'], '100 / 100')
        self.assertEqual(data['rubric_total'], '100/100')
        self.assertNotIn('calibrated_grade', data)
        self.assertIs(parse.call_args.kwargs['text_format'], app.GradingEvaluation)
        self.assertEqual(parse.call_args.kwargs['model'], 'gpt-6-astra')
        self.assertEqual(parse.call_args.kwargs['reasoning'], {'effort': 'medium'})

        report_data = {
            'student_name': data['student_name'], 'word_count': data['word_count'],
            'rubric_total': data['rubric_total'], 'overall_grade': data['grade'],
            'feedback': data['feedback'], 'criterion_feedback': data['criterion_feedback'],
            'timestamp': 'January 1, 2026',
        }
        pdf = BytesIO()
        app.generate_pdf(pdf, report_data)
        self.assertGreater(len(pdf.getvalue()), 0)

    def test_front_end_progress_hooks_are_preserved(self):
        javascript = (APP_DIR / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
        html = (APP_DIR / 'templates' / 'index.html').read_text(encoding='utf-8')
        server_source = (APP_DIR / 'app.py').read_text(encoding='utf-8')
        self.assertIn('showLoading(true)', javascript)
        self.assertIn('setInterval(updateElapsedTime, 1000)', javascript)
        self.assertIn('disableButtons(true)', javascript)
        self.assertIn('id="grade-value"', html)
        self.assertIn('Overall Grade', html)
        self.assertIn("[['Overall Grade', data['overall_grade']]]", server_source)


if __name__ == '__main__':
    unittest.main()
