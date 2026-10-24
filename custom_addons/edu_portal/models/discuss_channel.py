from odoo import api, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _subscribe_users_automatically_get_members(self):
        # Os canais que juntam todos os utilizadores internos (o «General») não juntam os alunos: as conversas são do
        # pessoal da escola.
        members = super()._subscribe_users_automatically_get_members()
        partners = self.env['res.partner'].sudo().browse({p for ids in members.values() for p in ids})
        students = partners.filtered(lambda p: p.user_ids and all(u._edu_student_only() for u in p.user_ids)).ids
        return {channel_id: [p for p in ids if p not in students] for channel_id, ids in members.items()}

    @api.model
    def _edu_remove_students(self, users=None):
        """Os alunos saem das conversas (as dos canais em que entraram antes de serem alunos, e as do OdooBot)."""
        if users is None:
            group = self.env.ref('edu_portal.group_edu_student', raise_if_not_found=False)
            users = group.sudo().all_user_ids if group else self.env['res.users']
        students = users.sudo().filtered(lambda u: u._edu_student_only())
        if students:
            self.env['discuss.channel.member'].sudo().search([('partner_id', 'in', students.partner_id.ids)]).unlink()
