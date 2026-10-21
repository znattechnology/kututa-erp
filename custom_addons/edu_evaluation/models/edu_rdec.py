from odoo import fields, models

RDEC_LEVELS = [
    ('not_satisfactory', 'Não satisfatório'),
    ('satisfactory', 'Satisfatório'),
    ('good', 'Bom'),
    ('very_good', 'Muito bom'),
]


class EduRdec(models.Model):
    """Relatório de Desempenho Escolar da Criança (iniciação): avaliação qualitativa, sem retenção (RAA, art. 19.º)."""

    _name = 'edu.rdec'
    _description = 'RDEC (iniciação)'
    _inherit = ['mail.thread']
    _order = 'trimester_id, id'
    _check_company_auto = True

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, check_company=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
    trimester_id = fields.Many2one('edu.trimester', string='Trimestre', required=True)
    appreciation = fields.Text(string='Apreciação global')
    line_ids = fields.One2many('edu.rdec.line', 'rdec_id', string='Áreas')

    _enrollment_trimester_uniq = models.Constraint(
        'UNIQUE(enrollment_id, trimester_id)', 'O aluno já tem RDEC neste trimestre.'
    )

    def action_fill_areas(self):
        for rdec in self:
            missing = rdec.enrollment_id.subject_ids - rdec.line_ids.subject_id
            self.env['edu.rdec.line'].create([{'rdec_id': rdec.id, 'subject_id': subject.id} for subject in missing])
        return True


class EduRdecLine(models.Model):
    _name = 'edu.rdec.line'
    _description = 'Área do RDEC'

    rdec_id = fields.Many2one('edu.rdec', required=True, ondelete='cascade')
    subject_id = fields.Many2one('edu.subject', string='Área', required=True)
    level = fields.Selection(RDEC_LEVELS, string='Nível')
    observations = fields.Text(string='Observações')
    company_id = fields.Many2one(related='rdec_id.company_id', store=True)
