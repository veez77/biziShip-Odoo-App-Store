from odoo import models


class BizishipLogoutWizard(models.TransientModel):
    _name = 'biziship.logout.wizard'
    _description = 'BiziShip Sign Out Confirmation'

    def action_logout(self):
        self.env.user.write({
            'biziship_token': False,
            'biziship_email': False,
            'biziship_user_name': False,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}
