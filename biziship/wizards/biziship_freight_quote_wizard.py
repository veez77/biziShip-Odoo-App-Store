import json
import requests
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import os
import logging

_logger = logging.getLogger(__name__)

from odoo.addons.biziship.api_utils import (
    get_biziship_api_url, 
    BIZISHIP_MODULE_VERSION, 
    BIZISHIP_APP_NAME,
    KG_TO_LBS,
    convert_to_lbs,
    convert_to_inches
)

class BizishipFreightQuoteWizard(models.TransientModel):
    _name = 'biziship.freight.quote.wizard'
    _description = 'Get Direct LTL Freight Quotes'

    order_id = fields.Many2one('sale.order', string="Sale Order", required=True)
    
    # Pre-filled Origin
    origin_company = fields.Char(string="Origin Company")
    origin_address = fields.Char(string="Origin Address Line 1", required=True)
    origin_address2 = fields.Char(string="Origin Address Line 2")
    origin_city = fields.Char(string="Origin City")
    origin_state = fields.Char(string="Origin State", help="2-letter abbreviation")
    origin_zip = fields.Char(string="Origin Zip Code", required=True)
    origin_country_id = fields.Many2one('res.country', string="Origin Country")
    origin_phone = fields.Char(string="Origin Phone")
    
    # Pre-filled Destination
    destination_company = fields.Char(string="Destination Company")
    destination_address = fields.Char(string="Destination Address Line 1", required=True)
    destination_address2 = fields.Char(string="Destination Address Line 2")
    destination_city = fields.Char(string="Destination City")
    destination_state = fields.Char(string="Destination State", help="2-letter abbreviation")
    destination_zip = fields.Char(string="Destination Zip Code", required=True)
    destination_country_id = fields.Many2one('res.country', string="Destination Country")
    destination_phone = fields.Char(string="Destination Phone")
    
    # Cargo Details (Multiple Lines)
    cargo_line_ids = fields.One2many('biziship.quote.cargo.line', 'wizard_id', string="Cargo Lines")
    
    total_weight = fields.Float(string="Total Weight", compute='_compute_totals', store=True)
    total_weight_unit = fields.Selection([('lbs', 'lbs'), ('kg', 'kg')], string="Weight Unit", default='lbs', required=True)
    
    cargo_description = fields.Char(string="Cargo Description", default="General Freight")

    # Accessorials
    biziship_origin_accessorial_ids = fields.Many2many('biziship.accessorial', 'biziship_wizard_origin_acc_rel', 'wizard_id', 'accessorial_id', string="Origin Accessorials")
    biziship_dest_accessorial_ids = fields.Many2many('biziship.accessorial', 'biziship_wizard_dest_acc_rel', 'wizard_id', 'accessorial_id', string="Destination Accessorials")
    
    biziship_origin_residential = fields.Boolean(string="Origin Residential")
    biziship_origin_liftgate = fields.Boolean(string="Origin Liftgate")
    biziship_origin_limited_access = fields.Boolean(string="Origin Limited Access")
    
    biziship_dest_residential = fields.Boolean(string="Destination Residential")
    biziship_dest_liftgate = fields.Boolean(string="Destination Liftgate")
    biziship_dest_limited_access = fields.Boolean(string="Destination Limited Access")
    biziship_dest_appointment = fields.Boolean(string="Destination Appointment")
    biziship_dest_notify = fields.Boolean(string="Destination Notify")
    biziship_dest_hazmat = fields.Boolean(string="Destination Hazmat")
    
    special_requirements = fields.Char(string="Special Requirements", help="Comma-separated. e.g. liftgate,residential_delivery")
    pickup_date = fields.Date(string="Pickup Date", required=True)
    additional_notes = fields.Text(string="Additional Notes")
    special_instructions = fields.Text(string="Special Instructions")

    @api.onchange('biziship_dest_residential')
    def _onchange_biziship_dest_residential(self):
        if self.biziship_dest_residential:
            self.biziship_dest_liftgate = True

    def action_uncheck_all_origin(self):
        for rec in self:
            rec.biziship_origin_residential = False
            rec.biziship_origin_liftgate = False
            rec.biziship_origin_limited_access = False
            rec.biziship_origin_accessorial_ids = [(5, 0, 0)]
        return {"type": "ir.actions.do_nothing"}

    def action_uncheck_all_dest(self):
        for rec in self:
            rec.biziship_dest_appointment = False
            rec.biziship_dest_residential = False
            rec.biziship_dest_notify = False
            rec.biziship_dest_limited_access = False
            rec.biziship_dest_liftgate = False
            rec.biziship_dest_hazmat = False
            rec.biziship_dest_accessorial_ids = [(5, 0, 0)]
        return {"type": "ir.actions.do_nothing"}

    @api.depends('cargo_line_ids', 'cargo_line_ids.weight', 'cargo_line_ids.weight_unit', 'cargo_line_ids.pieces', 'total_weight_unit')
    def _compute_totals(self):
        for rec in self:
            total_lbs = 0.0
            for line in rec.cargo_line_ids:
                total_lbs += convert_to_lbs(line.weight, line.weight_unit) * (line.pieces or 1)

            if rec.total_weight_unit == 'kg':
                rec.total_weight = round(total_lbs / KG_TO_LBS, 2)
            else:
                rec.total_weight = round(total_lbs, 2)

    @api.model
    def default_get(self, fields_list):
        res = super(BizishipFreightQuoteWizard, self).default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if not active_id:
            return res
            
        order = self.env['sale.order'].browse(active_id)
        if not order.exists():
            return res
            
        res['order_id'] = order.id
        
        # Origin mapping (Company warehouse)
        company = self.env.company
        res['origin_company'] = order.biziship_origin_company or company.name or ''
        res['origin_address'] = company.street or ''
        res['origin_address2'] = company.street2 or ''
        res['origin_city'] = company.city or ''
        res['origin_state'] = company.state_id.code if company.state_id else ''
        res['origin_zip'] = company.zip or '43341'
        res['origin_country_id'] = company.country_id.id if company.country_id else self.env.ref('base.us', raise_if_not_found=False).id
        res['origin_phone'] = company.phone or ''
        
        # Destination mapping (Customer)
        partner = order.partner_shipping_id or order.partner_id
        res['destination_company'] = order.biziship_dest_company or partner.name or ''
        res['destination_address'] = partner.street or ''
        res['destination_address2'] = partner.street2 or ''
        res['destination_city'] = partner.city or ''
        res['destination_state'] = partner.state_id.code if partner.state_id else ''
        res['destination_zip'] = partner.zip or '93036'
        res['destination_country_id'] = partner.country_id.id if partner.country_id else self.env.ref('base.us', raise_if_not_found=False).id
        res['destination_phone'] = partner.phone or ''
        
        # Automatically calculate weight from order lines if available
        total_weight = sum(line.product_id.weight * line.product_uom_qty for line in order.order_line if line.product_id)
        # Odoo's default demo products have a weight of 0.08, which overrides the 800.0 default. 
        # We enforce a minimum of 800.0 lbs for LTL quoting.
        res['total_weight'] = max(total_weight, 800.0)
        res['total_weight_unit'] = order.biziship_total_weight_unit or 'lbs'
        res['special_instructions'] = order.biziship_special_instructions or ''
            
        # Default Pickup Date to Tomorrow
        from datetime import timedelta
        res['pickup_date'] = fields.Date.context_today(self) + timedelta(days=1)

        # Prepopulate lines
        if 'cargo_line_ids' in fields_list or True:
            line_vals = []
            for so_line in order.biziship_cargo_line_ids:
                line_vals.append((0, 0, {
                    'packaging_type': so_line.packaging_type,
                    'pieces': so_line.pieces,
                    'weight': so_line.weight,
                    'weight_unit': so_line.weight_unit,
                    'length': so_line.length,
                    'width': so_line.width,
                    'height': so_line.height,
                    'dim_unit': so_line.dim_unit,
                    'freight_class': so_line.freight_class,
                    'cargo_desc': so_line.cargo_desc,
                }))
            if not line_vals: # Fallback single line if order has no cargo lines
                line_vals.append((0, 0, {
                    'weight': max(total_weight, 800.0),
                    'weight_unit': 'lbs',
                    'length': 48.0,
                    'width': 40.0,
                    'height': 48.0,
                    'dim_unit': 'in',
                    'pieces': 1,
                    'packaging_type': 'pallet',
                    'freight_class': '50',
                    'cargo_desc': 'General Freight'
                }))
            res['cargo_line_ids'] = line_vals
            
        return res

    def _format_phone(self, phone_str):
        if not phone_str:
            return ""
        digits = re.sub(r'\D', '', phone_str)
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    def action_get_quotes(self):
        self.ensure_one()
        
        # Validation
        if not self.cargo_line_ids:
            raise UserError(_("At least one cargo line is required to fetch LTL quotes."))
            
        for idx, line in enumerate(self.cargo_line_ids, start=1):
            if line.weight <= 0 or line.length <= 0 or line.width <= 0 or line.height <= 0:
                raise UserError(_("Cargo Line #%s has a missing or zero value. All cargo lines must have a Weight, Length, Width, and Height greater than 0.") % idx)
        
        email2quote_api_url = get_biziship_api_url(self.env)
        erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
        
        api_url = f"{email2quote_api_url.rstrip('/')}/erp/quote"
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "Content-Type": "application/json",
            "X-User-Email": (self.env.user.biziship_email if self.env.user.biziship_token and self.env.user.biziship_email else self.env.user.email) or "",
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
        }
        
        # Compile accessorials starting with tags
        accessorials_list = self.order_id.biziship_origin_accessorial_ids.mapped('code') + self.order_id.biziship_dest_accessorial_ids.mapped('code')
        
        # Origin Checkboxes
        if self.order_id.biziship_origin_residential: accessorials_list.append("RESPU")
        if self.order_id.biziship_origin_liftgate: accessorials_list.append("LGPU")
        if self.order_id.biziship_origin_limited_access: accessorials_list.append("LTDPU")
        
        # Destination Checkboxes
        if self.order_id.biziship_dest_residential: accessorials_list.append("RESDEL")
        if self.order_id.biziship_dest_liftgate: accessorials_list.append("LGDEL")
        if self.order_id.biziship_dest_limited_access: accessorials_list.append("LTDDEL")
        if self.order_id.biziship_dest_appointment: accessorials_list.append("APPT")
        if self.order_id.biziship_dest_notify: accessorials_list.append("NOTIFY")
        if self.order_id.biziship_dest_hazmat: accessorials_list.append("HAZM")
        
        accessorials_list = list(set(accessorials_list))  # Ensure uniqueness
        
        # Define missing format_phone 
        def format_phone(p):
            import re
            p = p or ""
            d = re.sub(r'\D', '', p)
            return d[-10:] if len(d) >= 10 else "5555555555"
        
        payload_items = []
        total_payload_weight = 0.0
        for line in self.cargo_line_ids:
            line_w_total = round(convert_to_lbs(line.weight, line.weight_unit) * (line.pieces or 1), 2)
            total_payload_weight += line_w_total
            payload_l = convert_to_inches(line.length, line.dim_unit)
            payload_w = convert_to_inches(line.width, line.dim_unit)
            payload_h = convert_to_inches(line.height, line.dim_unit)

            payload_items.append({
                "weight": line_w_total,
                "weight_unit": "lbs",
                "length": round(payload_l, 2),
                "width": round(payload_w, 2),
                "height": round(payload_h, 2),
                "dimension_unit": "inches",
                "num_pieces": line.pieces or 1,
                "total_pieces": 1,
                "packaging_type": line.packaging_type or "",
                "freight_class": line.freight_class or "",
                "cargo_description": line.cargo_desc or ""
            })

        payload = {
            "origin_company": self.origin_company or "",
            "origin_address": self.origin_address or "",
            "origin_address2": self.origin_address2 or "",
            "origin_city": self.origin_city or "",
            "origin_state": self.origin_state or "",
            "origin_zip": self.origin_zip or "43341",
            "origin_country": self.origin_country_id.code if self.origin_country_id else "US",
            "origin_phone": self._format_phone(self.origin_phone),
            "destination_company": self.destination_company or "",
            "destination_address": self.destination_address or "",
            "destination_address2": self.destination_address2 or "",
            "destination_city": self.destination_city or "",
            "destination_state": self.destination_state or "",
            "destination_zip": self.destination_zip or "93036",
            "destination_country": self.destination_country_id.code if self.destination_country_id else "US",
            "destination_phone": self._format_phone(self.destination_phone),
            "cargo_description": self.cargo_description or "",
            "special_instructions": self.order_id._biziship_merge_schedule_instructions(self.special_instructions) if self.order_id else (self.special_instructions or ""),
            "weight": round(total_payload_weight, 2),
            "weight_unit": "lbs",
            "line_items": payload_items,
            "accessorial_codes": accessorials_list,
            "pickup_date": str(self.pickup_date) if self.pickup_date else "",
            "additional_notes": self.additional_notes or ""
        }
        _logger.info("BiziShip Quote API Request Headers: %s", headers)
        _logger.info("BiziShip Quote API Request Payload: %s", json.dumps(payload, indent=2))
        
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=45)
            response.raise_for_status()
            
            response_json = response.json()
            quotes = response_json.get('quotes', [])
            
            # Capture environment from top level, then fetch full profile for demo_tries
            self.order_id.biziship_priority1_env = response_json.get('priority1_env', 'DEV')
            self.order_id._biziship_fetch_and_store_user_profile()
            
            if not quotes:
                raise UserError(_("No carrier quotes available for this lane. Check origin/destination zip codes or freight details."))
            
            # Save the JSON dict string directly to the sales order
            extracted_details = response_json.get('extracted_details', payload)
            self.order_id.write({'biziship_extracted_json': json.dumps(extracted_details)})
            
            # Clear old quotes before inserting new ones
            self.order_id.biziship_quote_ids.unlink()

            for q in quotes:
                delivery_date_raw = q.get('delivery_date')
                if delivery_date_raw and 'T' in delivery_date_raw:
                    delivery_date_raw = delivery_date_raw.replace('T', ' ')[:19]

                # Parse charges array into text
                charges = q.get('charges', [])
                details_lines = []
                for c in charges:
                    c_code = c.get('code', '')
                    c_desc = c.get('description', '')
                    c_amount = c.get('amount')
                    if c_amount is None:
                        c_amount = 0.0
                    details_lines.append(f"{str(c_desc):<40} ${c_amount:,.2f}")
                
                details_text = "\n".join(details_lines) if details_lines else "No detailed charges provided."

                self.env['biziship.quote'].sudo().create({
                    'sale_order_id': self.order_id.id,
                    'carrier_name': q.get('carrier_name'),
                    'carrier_code': q.get('carrier_code'),
                    'service_level': q.get('service_level'),
                    'transit_days': q.get('transit_days'),
                    'delivery_date': delivery_date_raw,
                    'total_charge': q.get('total_charge'),
                    'currency': q.get('currency', 'USD'),
                    'quote_id_ref': q.get('quote_id'),
                    'carrier_liability_new': q.get('carrier_liability_new'),
                    'carrier_liability_used': q.get('carrier_liability_used'),
                    'origin_address': extracted_details.get('origin_address'),
                    'origin_address2': extracted_details.get('origin_address2'),
                    'destination_address': extracted_details.get('destination_address'),
                    'destination_address2': extracted_details.get('destination_address2'),
                    'origin_terminal_city': extracted_details.get('origin_terminal_city'),
                    'origin_terminal_state': extracted_details.get('origin_terminal_state'),
                    'origin_terminal_phone': extracted_details.get('origin_terminal_phone'),
                    'destination_terminal_city': extracted_details.get('destination_terminal_city'),
                    'destination_terminal_state': extracted_details.get('destination_terminal_state'),
                    'destination_terminal_phone': extracted_details.get('destination_terminal_phone'),
                    'quote_details': details_text,
                })

            self.order_id._biziship_apply_quote_recommendation(
                response_json.get('recommended_quote_id'),
                response_json.get('recommendation_reason'),
            )

        except requests.exceptions.HTTPError as e:
            err_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_json = e.response.json()
                    if 'errors' in err_json and isinstance(err_json['errors'], list) and len(err_json['errors']) > 0:
                        err_msg = err_json['errors'][0]
                    else:
                        err_msg = err_json.get('detail', err_msg)
                except ValueError:
                    err_msg = e.response.text
            raise UserError(_("%s") % err_msg)
        except requests.exceptions.RequestException as e:
            raise UserError(_("Failed to connect to local Email2Quote API.\nEnsure server is running.\nDetails: %s") % str(e))

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
