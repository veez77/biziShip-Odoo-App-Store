from odoo import models


class BizishipNotConnectedWizard(models.TransientModel):
    _name = 'biziship.not.connected.wizard'
    _description = 'BiziShip Account Not Connected'

    def action_connect(self):
        # Forward sale_order_id so the auth wizard can update biziship_connected_email
        sale_order_id = self.env.context.get('active_id') if self.env.context.get('active_model') == 'sale.order' else None
        ctx = {'sale_order_id': sale_order_id} if sale_order_id else {}
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'biziship.auth.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': ctx,
        }
