def migrate(cr, version):
    """As anulações antigas tinham só o motivo em texto: «Desistente» passa a «Desistência»; as outras, «Outro»."""
    cr.execute(
        """
        UPDATE edu_enrollment
           SET drop_reason_code = CASE WHEN drop_reason ILIKE '%%desist%%' THEN 'withdrawal' ELSE 'other' END
         WHERE state = 'dropped' AND drop_reason_code IS NULL
        """
    )
