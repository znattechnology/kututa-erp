from odoo.addons.edu_attendance.models.absence_rules import (
    AT_RISK,
    FAILED,
    GENERAL,
    OK,
    TECHNICAL,
    absence_limit,
    absence_status,
)
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestAbsenceRules(BaseCase):
    def test_limits(self):
        # Casos do secPed (attendance.service.spec.ts).
        self.assertEqual([absence_limit(h, GENERAL) for h in (1, 2, 3, 6)], [3, 4, 5, 5])
        self.assertEqual([absence_limit(h, TECHNICAL) for h in (1, 2, 4)], [3, 6, 12])
        self.assertIsNone(absence_limit(0, GENERAL))
        self.assertIsNone(absence_limit(0, TECHNICAL))

    def test_status(self):
        self.assertEqual(absence_status(2, 4), OK)
        self.assertEqual(absence_status(3, 4), AT_RISK)
        self.assertEqual(absence_status(4, 4), FAILED)
        self.assertEqual(absence_status(9, None), OK)
