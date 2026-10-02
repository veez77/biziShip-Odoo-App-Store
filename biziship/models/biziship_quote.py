from odoo import models, fields, api, tools
import base64
import os

class BizishipQuote(models.Model):
    _name = 'biziship.quote'
    _description = 'BiziShip Freight Quote'
    _order = 'total_charge asc'

    display_name = fields.Char(compute='_compute_display_name')

    sale_order_id = fields.Many2one('sale.order', string='Sales Order', required=True, ondelete='cascade')
    carrier_name = fields.Char(string='Carrier')
    carrier_code = fields.Char(string='Carrier Code')
    service_level = fields.Char(string='Service Level')
    transit_days = fields.Integer(string='Transit Days')
    delivery_date = fields.Datetime(string='Delivery Date')
    total_charge = fields.Float(string='Total Charge')
    currency = fields.Char(string='Currency Code', default='USD')
    currency_id = fields.Many2one(related='sale_order_id.currency_id')
    quote_id_ref = fields.Char(string="Quote ID Ref") # Changed string from 'Quote ID' to 'Quote ID Ref'

    carrier_liability_new = fields.Float(string='Carrier Liability New')
    carrier_liability_used = fields.Float(string='Carrier Liability Used')


    # New Address & Terminal Fields
    origin_address = fields.Char(string="Origin Address")
    origin_address2 = fields.Char(string="Origin Address 2")
    destination_address = fields.Char(string="Destination Address")
    destination_address2 = fields.Char(string="Destination Address 2")
    
    origin_terminal_city = fields.Char(string="Origin Terminal City")
    origin_terminal_state = fields.Char(string="Origin Terminal State")
    origin_terminal_phone = fields.Char(string="Origin Terminal Phone")
    
    destination_terminal_city = fields.Char(string="Destination Terminal City")
    destination_terminal_state = fields.Char(string="Destination Terminal State")
    destination_terminal_phone = fields.Char(string="Destination Terminal Phone")

    is_selected = fields.Boolean(string='Selected', default=False)
    quote_details = fields.Text(string='Quote Details')
    carrier_logo = fields.Binary(string="Carrier Logo", compute="_compute_carrier_logo")

    # AI carrier recommendation (from /erp/quote's recommended_quote_id + recommendation_reason,
    # when present - null whenever a recommendation isn't available, which is the normal default).
    is_recommended = fields.Boolean(string='Recommended', default=False, copy=False)
    recommendation_reason = fields.Char(string='Recommendation Reason', copy=False)
    biziship_recommendation_html = fields.Html(
        string='Recommendation', compute='_compute_biziship_recommendation_html',
        sanitize=False, readonly=True,
    )

    @api.depends('is_recommended', 'recommendation_reason')
    def _compute_biziship_recommendation_html(self):
        import html as _html
        for rec in self:
            if not rec.is_recommended:
                rec.biziship_recommendation_html = False
                continue
            reason = _html.escape(rec.recommendation_reason or '')
            rec.biziship_recommendation_html = (
                '<div class="biziship-rec-wrap">'
                '<span class="biziship-rec-badge">Recommended</span>'
                '<a href="#" class="biziship-why-toggle">Why?</a>'
                f'<div class="biziship-why-reason">{reason}</div>'
                '</div>'
            )

    # Residential address booking-time acknowledgment - reset fresh on every booking
    # attempt (see sale.order.action_open_biziship_quote_confirm), only set True via
    # biziship.residential.warning.wizard's explicit override. Sent to /erp/book as
    # origin_residential_risk_acknowledged / destination_residential_risk_acknowledged,
    # omitted entirely when False.
    origin_residential_risk_acknowledged = fields.Boolean(default=False, copy=False)
    destination_residential_risk_acknowledged = fields.Boolean(default=False, copy=False)

    biziship_cargo_line_ids = fields.One2many(related='sale_order_id.biziship_cargo_line_ids', string='Cargo Lines')
    biziship_total_weight = fields.Float(related='sale_order_id.biziship_total_weight', string='Total Weight')
    biziship_total_weight_unit = fields.Selection(related='sale_order_id.biziship_total_weight_unit', string='Weight Unit')

    @api.depends('carrier_name', 'carrier_code')
    def _compute_carrier_logo(self):
        mapping = {
            'fedex': 'fedex1.png',
            'r&l': 'RLCarriers.jpg',
            'rl': 'RLCarriers.jpg',
            'r l': 'RLCarriers.jpg',
            'r+l': 'RLCarriers.jpg',
            'abf': 'abf.png',
            'averitt': 'averitt.ico',
            'dayton': 'dayton.png',
            'estes': 'estes.png',
            'old dominion': 'odfl.ico',
            'odfl': 'odfl.ico',
            'pitt': 'pittohio.png',
            'saia': 'saia.ico',
            'south': 'sefl.ico',
            'sefl': 'sefl.ico',
            'tforce': 'tforce.png',
            't-force': 'tforce.png',
            'xpo': 'xpo.ico',
            'aaa': 'aaa.png',
            'mountain valley': 'Mountain_Valley_Express.jpg',
            'numark': 'Numark_Transportation.jpg',
            'unis': 'UNIS.png',
            'roadrunner': 'Roadrunner_Transportation_Systems.jpg',
            'best overnite': 'Best_Overnight_Express.png',
            'best overnight': 'Best_Overnight_Express.png',
            'xpress global': 'Express_Global_Systems_Llc.jpg',
            'warp': 'WARP.png'
        }
        
        for rec in self:
            logo_data = False
            name_lower = (rec.carrier_name or '').lower()
            code_lower = (rec.carrier_code or '').lower()
            
            best_match = None
            for key, filename in mapping.items():
                if key in name_lower or key in code_lower:
                    best_match = filename
                    break
                    
            if best_match:
                try:
                    img_path = tools.file_path('biziship/static/carriers/' + best_match)
                    if img_path and os.path.exists(img_path):
                        try:
                            with open(img_path, 'rb') as f:
                                logo_data = base64.b64encode(f.read())
                        except Exception:
                            pass
                except Exception:
                    pass
            
            rec.carrier_logo = logo_data

    def action_select_quote_toggle(self):
        for record in self:
            if record.is_selected:
                record.is_selected = False
            else:
                self.search([
                    ('sale_order_id', '=', record.sale_order_id.id),
                    ('id', '!=', record.id),
                    ('is_selected', '=', True)
                ]).write({'is_selected': False})
                record.is_selected = True
        return True

    def write(self, vals):
        if vals.get('is_selected'):
            # If we are setting this quote to selected, deselect others for the same order
            for record in self:
                other_quotes = self.env['biziship.quote'].search([
                    ('sale_order_id', '=', record.sale_order_id.id),
                    ('id', '!=', record.id),
                    ('is_selected', '=', True)
                ])
                if other_quotes:
                    other_quotes.write({'is_selected': False})
        return super().write(vals)

    @api.depends('carrier_name', 'total_charge', 'currency')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.carrier_name} - {record.total_charge} {record.currency}"
