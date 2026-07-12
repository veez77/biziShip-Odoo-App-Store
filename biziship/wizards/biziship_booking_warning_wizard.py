from odoo import models, fields, api, _

class BizishipBookingWarningWizard(models.TransientModel):
    _name = 'biziship.booking.warning.wizard'
    _description = 'Live Freight Booking Warning'

    quote_confirm_wizard_id = fields.Many2one('biziship.quote.confirm.wizard', string="Quote Confirm Wizard")
    quote_id = fields.Many2one('biziship.quote', string="Quote", required=True)

    def action_confirm_and_book(self):
        self.ensure_one()
        # Open the confirmation wizard for this quote
        return {
            'name': 'Confirm Quote Selection',
            'type': 'ir.actions.act_window',
            'res_model': 'biziship.quote.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quote_id': self.quote_id.id,
                'biziship_warning_confirmed': True,
            }
        }
