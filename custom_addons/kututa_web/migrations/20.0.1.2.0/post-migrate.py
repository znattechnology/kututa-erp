def migrate(cr, version):
    cr.execute('UPDATE res_users SET tour_enabled = FALSE WHERE tour_enabled')
    cr.execute(
        "UPDATE res_users SET odoobot_state = 'disabled' "
        "WHERE odoobot_state IS NULL OR odoobot_state = 'not_initialized'"
    )
