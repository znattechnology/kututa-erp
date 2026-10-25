from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain


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

    @api.model
    def _edu_check_chat_partners(self, partners):
        """O aluno e o encarregado só abrem conversas com os contactos do secPed (a lista da «Nova conversa»), também
        quando pedem a conversa directamente ao servidor."""
        if self.env.su:
            return
        allowed = self.env.user._edu_chat_partners()
        if allowed is not None and partners - self.env.user.partner_id - allowed:
            raise AccessError(
                self.env._('Só podes escrever aos professores da turma, ao director de turma e à secretaria.')
            )

    def _add_members(self, *, guests=None, partners=None, users=None, **kwargs):
        # Os membros juntam-se em sudo: a verificação dos novos membros não chega lá.
        self._edu_check_chat_partners(
            (partners or self.env['res.partner']) | (users or self.env['res.users']).partner_id
        )
        return super()._add_members(guests=guests, partners=partners, users=users, **kwargs)


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    @api.model_create_multi
    def create(self, vals_list):
        # As conversas novas (a dois ou em grupo) do aluno e do encarregado: só com os contactos do secPed.
        partner_ids = {vals['partner_id'] for vals in vals_list if vals.get('partner_id')}
        self.env['discuss.channel']._edu_check_chat_partners(self.env['res.partner'].browse(partner_ids))
        return super().create(vals_list)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_channel_invite_domain(self, channel, with_portal_users=False):
        # A procura da «Nova conversa» do aluno e do encarregado: só os contactos do secPed (como a lista de cima).
        domain = super()._get_channel_invite_domain(channel, with_portal_users)
        allowed = self.env.user._edu_chat_partners()
        if allowed is not None:
            domain &= Domain('id', 'in', allowed.ids)
        return domain
