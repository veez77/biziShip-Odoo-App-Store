import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BizishipAddressHistoryLine(models.TransientModel):
    _name = 'biziship.address.history.line'
    _description = 'Previous Address Line'

    wizard_id = fields.Many2one('biziship.address.history.wizard', ondelete='cascade')
    is_selected = fields.Boolean(default=False)

    company_name = fields.Char()
    address = fields.Char()
    address2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state')
    zip_code = fields.Char()
    country_id = fields.Many2one('res.country')
    contact_name = fields.Char()
    contact_phone = fields.Char()
    contact_email = fields.Char()
    # Recurring weekly hours JSON used on the source order (pickup for origin, delivery for dest)
    hours_json = fields.Char()
    # Accessorial codes (comma-joined) and checkbox flags (JSON) from the source order
    accessorial_codes = fields.Char()
    flags_json = fields.Char()
    source_order_name = fields.Char(string='From Quote')
    source_date = fields.Char(string='Date')

    address_display = fields.Char(compute='_compute_display', store=False)
    contact_display = fields.Char(compute='_compute_display', store=False)

    @api.depends('address', 'address2', 'city', 'state_id', 'zip_code', 'contact_name', 'contact_phone')
    def _compute_display(self):
        for rec in self:
            street = ' | '.join(filter(None, [rec.address, rec.address2]))
            city_state = ', '.join(filter(None, [
                rec.city,
                rec.state_id.code if rec.state_id else '',
                rec.zip_code,
            ]))
            rec.address_display = '  ·  '.join(filter(None, [street, city_state]))
            rec.contact_display = '  |  '.join(filter(None, [rec.contact_name, rec.contact_phone]))

    @api.onchange('is_selected')
    def _onchange_is_selected(self):
        if self.is_selected and self.wizard_id:
            for line in self.wizard_id.address_line_ids:
                if line != self:
                    line.is_selected = False


class BizishipAddressHistoryWizard(models.TransientModel):
    _name = 'biziship.address.history.wizard'
    _description = 'Previous Address History'

    sale_order_id = fields.Many2one('sale.order')
    address_type = fields.Selection([('origin', 'Origin'), ('destination', 'Destination')], default='origin')
    search_query = fields.Char(string='Filter')
    address_line_ids = fields.One2many('biziship.address.history.line', 'wizard_id')

    def _load_address_lines(self, search_query=''):
        is_dest = self.address_type == 'destination'
        addr_field = 'biziship_dest_address' if is_dest else 'biziship_origin_address'
        domain = [
            ('company_id', '=', self.env.company.id),
            (addr_field, '!=', False),
            (addr_field, '!=', ''),
        ]
        orders = self.env['sale.order'].search(domain, order='date_order desc, id desc', limit=500)

        def _val(order, origin_f, dest_f):
            return getattr(order, dest_f if is_dest else origin_f, '') or ''

        def _id(order, origin_f, dest_f):
            rec = getattr(order, dest_f if is_dest else origin_f, False)
            return rec.id if rec else False

        seen = set()
        lines = []
        for order in orders:
            company  = _val(order, 'biziship_origin_company',    'biziship_dest_company')
            address  = _val(order, 'biziship_origin_address',    'biziship_dest_address')
            city     = _val(order, 'biziship_origin_city',       'biziship_dest_city')
            state_id = _id(order,  'biziship_origin_state_id',   'biziship_dest_state_id')
            zip_code = _val(order, 'biziship_origin_zip',        'biziship_dest_zip')

            key = (company.strip().lower(), address.strip().lower(),
                   city.strip().lower(), state_id or 0, zip_code.strip().lower())
            if key in seen:
                continue
            seen.add(key)

            # Capture accessorial codes + checkbox flags from the source order for this side.
            if is_dest:
                acc_codes = order.biziship_dest_accessorial_ids.mapped('code')
                flags = {
                    'appointment':    order.biziship_dest_appointment,
                    'residential':    order.biziship_dest_residential,
                    'notify':         order.biziship_dest_notify,
                    'limited_access': order.biziship_dest_limited_access,
                    'liftgate':       order.biziship_dest_liftgate,
                    'hazmat':         order.biziship_dest_hazmat,
                }
            else:
                acc_codes = order.biziship_origin_accessorial_ids.mapped('code')
                flags = {
                    'residential':    order.biziship_origin_residential,
                    'liftgate':       order.biziship_origin_liftgate,
                    'limited_access': order.biziship_origin_limited_access,
                }

            if search_query:
                q = search_query.strip().lower()
                state_rec = getattr(order, 'biziship_dest_state_id' if is_dest else 'biziship_origin_state_id', False)
                contact   = _val(order, 'biziship_origin_contact_name', 'biziship_dest_contact_name')
                haystack = ' '.join(filter(None, [
                    company, address,
                    _val(order, 'biziship_origin_address2', 'biziship_dest_address2'),
                    city, state_rec.name if state_rec else '', zip_code, contact,
                ])).lower()
                if q not in haystack:
                    continue

            lines.append({
                'company_name': company,
                'address':      address,
                'address2':     _val(order, 'biziship_origin_address2',     'biziship_dest_address2'),
                'city':         city,
                'state_id':     state_id,
                'zip_code':     zip_code,
                'country_id':   _id(order, 'biziship_origin_country_id',    'biziship_dest_country_id'),
                'contact_name': _val(order, 'biziship_origin_contact_name', 'biziship_dest_contact_name'),
                'contact_phone':_val(order, 'biziship_origin_contact_phone','biziship_dest_contact_phone'),
                'contact_email':_val(order, 'biziship_origin_contact_email','biziship_dest_contact_email'),
                'hours_json':   _val(order, 'biziship_origin_pickup_hours', 'biziship_dest_delivery_hours'),
                'accessorial_codes': ','.join(acc_codes),
                'flags_json':   json.dumps(flags),
                'source_order_name': order.name or '',
                'source_date': order.date_order.strftime('%b %d, %Y') if order.date_order else '',
            })
        return lines

    @api.onchange('search_query')
    def _onchange_search_query(self):
        lines = self._load_address_lines(self.search_query or '')
        self.address_line_ids = [(5, 0, 0)] + [(0, 0, l) for l in lines]

    def action_filter(self):
        """Called by the Filter button — re-runs the search and reopens the wizard."""
        self.ensure_one()
        lines = self._load_address_lines(self.search_query or '')
        self.address_line_ids = [(5, 0, 0)]
        for l in lines:
            self.env['biziship.address.history.line'].create(dict(l, wizard_id=self.id))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'biziship.address.history.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @staticmethod
    def _parse_flags(raw):
        try:
            return json.loads(raw or '{}') or {}
        except (ValueError, TypeError):
            return {}

    def _match_accessorials(self, codes_csv, acc_type):
        """Resolve comma-joined accessorial codes to records of the given type ('origin'/'destination')."""
        codes = [c for c in (codes_csv or '').split(',') if c]
        if not codes:
            return self.env['biziship.accessorial']
        return self.env['biziship.accessorial'].search([
            ('code', 'in', codes),
            ('type', '=', acc_type),
        ])

    def action_apply_address(self):
        self.ensure_one()
        selected = self.address_line_ids.filtered('is_selected')
        if not selected:
            raise UserError('Please select an address from the list first.')
        sel = selected[0]
        so = self.sale_order_id
        is_dest = self.address_type == 'destination'

        if is_dest:
            dest_vals = {
                'biziship_dest_company':       sel.company_name,
                'biziship_dest_address':       sel.address,
                'biziship_dest_address2':      sel.address2,
                'biziship_dest_city':          sel.city,
                'biziship_dest_state_id':      sel.state_id.id if sel.state_id else False,
                'biziship_dest_zip':           sel.zip_code,
                'biziship_dest_country_id':    sel.country_id.id if sel.country_id else False,
                'biziship_dest_contact_name':  sel.contact_name,
                'biziship_dest_contact_phone': sel.contact_phone,
                'biziship_dest_contact_email': sel.contact_email,
            }
            # Restore the delivery hours + weekdays used on that previous booking (skip if none saved).
            if sel.hours_json:
                dest_vals['biziship_dest_delivery_hours'] = sel.hours_json
            # Restore the checkbox flags + accessorial services from that previous booking.
            flags = self._parse_flags(sel.flags_json)
            dest_vals.update({
                'biziship_dest_appointment':    bool(flags.get('appointment')),
                'biziship_dest_residential':    bool(flags.get('residential')),
                'biziship_dest_notify':         bool(flags.get('notify')),
                'biziship_dest_limited_access': bool(flags.get('limited_access')),
                'biziship_dest_liftgate':       bool(flags.get('liftgate')),
                'biziship_dest_hazmat':         bool(flags.get('hazmat')),
                'biziship_dest_accessorial_ids': [(6, 0, self._match_accessorials(sel.accessorial_codes, 'destination').ids)],
            })
            so.write(dest_vals)
            so._biziship_run_address_validation(
                sel.address, sel.city,
                sel.state_id.code if sel.state_id else '',
                sel.zip_code, 'destination',
            )
        else:
            origin_vals = {
                'biziship_origin_company':       sel.company_name,
                'biziship_origin_address':       sel.address,
                'biziship_origin_address2':      sel.address2,
                'biziship_origin_city':          sel.city,
                'biziship_origin_state_id':      sel.state_id.id if sel.state_id else False,
                'biziship_origin_zip':           sel.zip_code,
                'biziship_origin_country_id':    sel.country_id.id if sel.country_id else False,
                'biziship_origin_contact_name':  sel.contact_name,
                'biziship_origin_contact_phone': sel.contact_phone,
                'biziship_origin_contact_email': sel.contact_email,
            }
            # Restore the pickup hours + weekdays used on that previous booking (skip if none saved).
            if sel.hours_json:
                origin_vals['biziship_origin_pickup_hours'] = sel.hours_json
            # Restore the checkbox flags + accessorial services from that previous booking.
            flags = self._parse_flags(sel.flags_json)
            origin_vals.update({
                'biziship_origin_residential':    bool(flags.get('residential')),
                'biziship_origin_liftgate':       bool(flags.get('liftgate')),
                'biziship_origin_limited_access': bool(flags.get('limited_access')),
                'biziship_origin_accessorial_ids': [(6, 0, self._match_accessorials(sel.accessorial_codes, 'origin').ids)],
            })
            so.write(origin_vals)
            so._biziship_run_address_validation(
                sel.address, sel.city,
                sel.state_id.code if sel.state_id else '',
                sel.zip_code, 'origin',
            )
        return {'type': 'ir.actions.act_window_close'}
