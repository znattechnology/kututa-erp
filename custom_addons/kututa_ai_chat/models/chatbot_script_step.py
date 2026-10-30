from odoo import fields, models
from odoo.tools import html2plaintext, plaintext2html


class ChatbotScriptStep(models.Model):
    _inherit = 'chatbot.script.step'

    step_type = fields.Selection(
        selection_add=[('kututa_ia', 'Conversa com IA')],
        ondelete={'kututa_ia': 'cascade'},
    )

    def _process_answer(self, discuss_channel, message_body):
        # A conversa com a IA não avança no guião: cada resposta do visitante volta a este mesmo passo.
        if self.step_type == 'kututa_ia':
            return self
        return super()._process_answer(discuss_channel, message_body)

    def _process_step(self, discuss_channel):
        self.ensure_one()
        if self.step_type != 'kututa_ia':
            return super()._process_step(discuss_channel)
        channel = discuss_channel.sudo()
        bot = self.chatbot_script_id.operator_partner_id
        # sudo: mail.message - a última mensagem do visitante (não do bot) neste canal.
        last = (
            self.env['mail.message']
            .sudo()
            .search(
                [('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('message_type', '=', 'comment')],
                order='id desc',
                limit=1,
            )
        )
        if not last or last.author_id == bot:
            # Entrada no passo: a saudação, com o aviso de que é um assistente automático.
            return {'message': channel._chatbot_post_message(self.chatbot_script_id, self.message)}
        reply = self.env['kututa.ia.agente']._responder(channel, html2plaintext(last.body or ''))
        message = channel._chatbot_post_message(self.chatbot_script_id, plaintext2html(reply.text))
        if reply.handover:
            channel._forward_human_operator()
        return {'message': message}
