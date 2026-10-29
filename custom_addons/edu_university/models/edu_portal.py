from odoo import api, models
from odoo.addons.edu_portal.models.edu_student_portal import grade_text

from .edu_uc_registration import FREQUENCY_STATUSES, SOURCES, STATES

SEMESTER_LABELS = {'1': '1.º sem.', '2': '2.º sem.', 'annual': 'Anual'}


class EduStudentPortal(models.AbstractModel):
    """No superior, «Minhas notas» mostra as UCs do ano: as provas de frequência e os trabalhos, a MF, a situação, os
    exames e a nota final, com os créditos obtidos no curso."""

    _inherit = 'edu.student.portal'

    @api.private
    @api.model
    def grades(self, student, enrollment, trimester_id=None):
        if not enrollment or enrollment.level_subsystem != 'higher':
            return super().grades(student, enrollment, trimester_id=trimester_id)
        edu_class = enrollment.class_id
        data = {
            'higher': True,
            'blocked': False,
            'preschool': False,
            'trimesters': [],
            'subjects': [],
            'trend': [],
            'active': None,
            'components': 0,
            'summary': '',
            'year_average': None,
            'year_result': self._year_result(enrollment),
            'scale_max': 20,
            'year': enrollment.academic_year_id.name,
            'class': edu_class._editor_label(),
            'level': edu_class.level_id.name or '',
            'past': not enrollment.academic_year_id.is_current,
        }
        blocked, _message = student._edu_gate('grades')
        if blocked:
            data['blocked'] = True
            return data
        regulation = self.env['edu.university.regulation']._get(enrollment.company_id, enrollment.course_id.level_id)
        data.update({'pass_grade': regulation.pass_grade, 'pass_text': grade_text(regulation.pass_grade)})
        statuses, sources, states = dict(FREQUENCY_STATUSES), dict(SOURCES), dict(STATES)

        def cell(value, flag=True):
            if not flag:
                return None
            return {'text': grade_text(value), 'pos': value >= regulation.pass_grade, 'value': round(value, 2)}

        rows = []
        for registration in enrollment.uc_registration_ids.sudo().sorted(
            lambda r: (r.semester or '', r.course_year, r.subject_id.name or '')
        ):
            components = [
                {
                    'name': grade.assessment_id.name,
                    'value': cell(grade.score * 20 / (grade.assessment_id.max_score or 20)),
                }
                for grade in self.env['edu.grade']
                .sudo()
                .search(
                    [
                        ('enrollment_id', '=', enrollment.id),
                        ('subject_id', '=', registration.subject_id.id),
                        ('class_id', '=', registration.class_id.id),
                        ('graded', '=', True),
                    ],
                    order='id',
                )
            ]
            exams = [
                {'label': label, 'value': cell(registration[name], registration[f'has_{name}'])}
                for name, label in (
                    ('exam_normal', 'Exame'),
                    ('exam_appeal', 'Recurso'),
                    ('exam_special', 'Especial'),
                    ('exam_improvement', 'Melhoria'),
                )
                if registration[f'has_{name}']
            ]
            rows.append(
                {
                    'id': registration.id,
                    'name': registration.subject_id.name,
                    'code': registration.subject_id.code or '',
                    'semester': SEMESTER_LABELS.get(registration.semester, ''),
                    'year': registration.course_year,
                    'credits': registration.credits,
                    'backlog': registration.is_backlog,
                    'components': components,
                    'mf': cell(registration.frequency_mark, registration.has_frequency_mark),
                    'attendance': round(registration.attendance_rate) if registration.has_attendance else None,
                    'status': statuses.get(registration.frequency_status, ''),
                    'status_key': registration.frequency_status,
                    'exams': exams,
                    'final': cell(registration.final_grade, registration.has_final),
                    'source': sources.get(registration.result_source, ''),
                    'state': states.get(registration.state, ''),
                    'state_key': registration.state,
                }
            )
        passed = enrollment._edu_uc_transcript()
        course_credits = enrollment.class_id.curriculum_id.total_credits
        earned = sum(passed.mapped('credits'))
        average = sum(r.final_grade * r.credits for r in passed) / earned if earned else None
        data.update(
            {
                'ucs': rows,
                'credits_year': sum(r['credits'] for r in rows if r['state_key'] != 'dropped'),
                'credits_earned': earned,
                'credits_course': course_credits,
                'credits_pct': round(100 * earned / course_credits) if course_credits else 0,
                'course_average': cell(average, average is not None),
                'passed_count': len([r for r in rows if r['state_key'] == 'passed']),
                'exam_count': len([r for r in rows if r['status_key'] == 'admitted' and r['state_key'] != 'passed']),
            }
        )
        return data
