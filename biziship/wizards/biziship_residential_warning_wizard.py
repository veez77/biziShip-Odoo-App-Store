from odoo import models, fields, api, _


class BizishipResidentialWarningWizard(models.TransientModel):
    _name = 'biziship.residential.warning.wizard'
    _description = 'Residential Address Not Flagged Warning'

    quote_id = fields.Many2one('biziship.quote', string="Quote", required=True)
    origin_flagged = fields.Boolean(string="Origin Flagged")
    destination_flagged = fields.Boolean(string="Destination Flagged")

    origin_address_display = fields.Char(compute='_compute_address_display')
    destination_address_display = fields.Char(compute='_compute_address_display')

    @api.depends('quote_id')
    def _compute_address_display(self):
        for rec in self:
            so = rec.quote_id.sale_order_id
            if not so:
                rec.origin_address_display = ''
                rec.destination_address_display = ''
                continue
            rec.origin_address_display = rec._biziship_format_address(
                so.biziship_origin_address, so.biziship_origin_city,
                so.biziship_origin_state_id.code, so.biziship_origin_zip,
            )
            rec.destination_address_display = rec._biziship_format_address(
                so.biziship_dest_address, so.biziship_dest_city,
                so.biziship_dest_state_id.code, so.biziship_dest_zip,
            )

    def _biziship_format_address(self, address, city, state, zip_code):
        city_state_zip = ', '.join(p for p in [city, state] if p)
        if zip_code:
            city_state_zip = f"{city_state_zip} {zip_code}".strip()
        return ', '.join(p for p in [address, city_state_zip] if p)

    def action_go_back(self):
        return {'type': 'ir.actions.act_window_close'}

    def action_acknowledge_and_continue(self):
        self.ensure_one()
        vals = {}
        if self.origin_flagged:
            vals['origin_residential_risk_acknowledged'] = True
        if self.destination_flagged:
            vals['destination_residential_risk_acknowledged'] = True
        if vals:
            self.quote_id.write(vals)
        return self.quote_id.sale_order_id._biziship_quote_confirm_next_step(self.quote_id)
