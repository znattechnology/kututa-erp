from odoo import models

from ..models.listings import EM


class EduEnrollmentConfirmation(models.TransientModel):
    _inherit = 'edu.enrollment.confirmation'

    def action_print_listing(self):
        self.ensure_one()
        return self.env.ref('edu_documents.action_report_listing_confirmation').preview_action(self)

    def _listing_data(self):
        self.ensure_one()
        groups = []
        for state, label in self.line_ids._fields['state']._description_selection(self.env):
            rows = self.line_ids.filtered(lambda line, st=state: line.state == st)
            if rows:
                groups.append(
                    {
                        'label': label,
                        'rows': [
                            [
                                line.student_id.name,
                                line.previous_class_id._editor_label() if line.previous_class_id else '',
                                line.target_class_id._editor_label() if line.target_class_id else '',
                                line.reason or '',
                            ]
                            for line in rows
                        ],
                    }
                )
        return {
            'title': self.env._('CONFIRMAÇÃO DE MATRÍCULAS'),
            'context': EM.join([f'{self.source_year_id.name} → {self.target_year_id.name}', self.summary or '']),
            'columns': [
                (self.env._('Aluno'), 0, 'l'),
                (self.env._('Turma anterior'), 14, 'l'),
                (self.env._('Turma de destino'), 14, 'l'),
                (self.env._('Motivo'), 34, 'l'),
            ],
            'groups': groups,
        }
