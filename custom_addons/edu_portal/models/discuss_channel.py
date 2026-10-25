from odoo import api, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _subscribe_users_automatically_get_members(self):
        # Os canais que juntam todos os utilizadores internos (o «General») não juntam os alunos nem os encarregados:
        # os canais são do pessoal da escola.
        members = super()._subscribe_users_automatically_get_members()
        partners = self.env['res.partner'].sudo().browse({p for ids in members.values() for p in ids})
        family = partners.filtered(
            lambda p: p.user_ids and all(u._edu_student_only() or u._edu_guardian_only() for u in p.user_ids)
        ).ids
        return {channel_id: [p for p in ids if p not in family] for channel_id, ids in members.items()}

    @api.model
    def _edu_remove_family(self, users=None):
        """Os alunos e os encarregados saem dos canais do pessoal (o «General» junta todos os internos); ficam as suas
        conversas com a escola."""
        if users is None:
            groups = [
                self.env.ref(xmlid, raise_if_not_found=False)
                for xmlid in ('edu_portal.group_edu_student', 'edu_portal.group_edu_guardian')
            ]
            users = self.env['res.users'].union(*(g.sudo().all_user_ids for g in groups if g))
        family = users.sudo().filtered(lambda u: u._edu_student_only() or u._edu_guardian_only())
        if family:
            self.env['discuss.channel.member'].sudo().search(
                [('partner_id', 'in', family.partner_id.ids), ('channel_id.channel_type', '=', 'channel')]
            ).unlink()
