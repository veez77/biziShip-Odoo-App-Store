import requests
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from odoo.addons.biziship import api_utils
from odoo.addons.biziship.api_utils import get_erp_api_key, BIZISHIP_APP_NAME, BIZISHIP_MODULE_VERSION

class BizishipSaveFreightWizard(models.TransientModel):
    _name = 'biziship.save.freight.wizard'
    _description = 'Save Freight to My Pool'

    name = fields.Char(string='Freight Name', required=True)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')

    def action_save_freight(self):
        self.ensure_one()
        token = self.env.user.biziship_token
        if not token:
            raise UserError(_("Please connect your BiziShip account first in your User Profile."))

        order = self.sale_order_id
        
        # Prepare line items for JSON stringified field
        cargo_lines = []
        for line in order.biziship_cargo_line_ids:
            cargo_lines.append({
                "packaging_type": line.packaging_type,
                "num_pieces": line.pieces,
                "weight": line.weight,
                "weight_unit": (line.weight_unit or order.biziship_total_weight_unit or "lbs").lower()[:3],
                "length": line.length,
                "width": line.width,
                "height": line.height,
                "dim_unit": line.dim_unit or "in",
                "freight_class": line.computed_freight_class or line.freight_class,
                "cargo_description": line.cargo_desc,
                "nmfc": line.nmfc or "",
            })

        # Prepare freight details mirroring the web app structure precisely
        # IMPORTANT: use web app's ManualFormState key names so the freight loads correctly
        from datetime import date as date_type
        today_str = date_type.today().isoformat()
        pickup_date_str = order.biziship_pickup_date.isoformat() if order.biziship_pickup_date else today_str
        # Advance past dates to today (web app does the same)
        if pickup_date_str < today_str:
            pickup_date_str = today_str

        def _parse_hours(raw):
            try:
                return json.loads(raw or '{}') or {}
            except (ValueError, TypeError):
                return {}
        _origin_hours = _parse_hours(order.biziship_origin_pickup_hours)
        _dest_hours = _parse_hours(order.biziship_dest_delivery_hours)

        freight_details = {
            "origin_company":       order.biziship_origin_company or None,
            "origin_address":       order.biziship_origin_address or None,
            "origin_address2":      order.biziship_origin_address2 or None,
            "origin_city":          order.biziship_origin_city or None,
            "origin_state":         order.biziship_origin_state_id.code if order.biziship_origin_state_id else None,
            "origin_zip":           order.biziship_origin_zip or None,
            "origin_country":       order.biziship_origin_country_id.code if order.biziship_origin_country_id else "US",
            # Contact fields — use web app ManualFormState field names
            "origin_contact_name":  order.biziship_origin_contact_name or None,
            "origin_contact_phone": order.biziship_origin_contact_phone or None,
            "origin_contact_email": order.biziship_origin_contact_email or None,

            "dest_company":         order.biziship_dest_company or None,
            "dest_address":         order.biziship_dest_address or None,
            "dest_address2":        order.biziship_dest_address2 or None,
            "dest_city":            order.biziship_dest_city or None,
            "dest_state":           order.biziship_dest_state_id.code if order.biziship_dest_state_id else None,
            "dest_zip":             order.biziship_dest_zip or None,
            "dest_country":         order.biziship_dest_country_id.code if order.biziship_dest_country_id else "US",
            # Contact fields — use web app ManualFormState field names
            "dest_contact_name":    order.biziship_dest_contact_name or None,
            "dest_contact_phone":   order.biziship_dest_contact_phone or None,
            "dest_contact_email":   order.biziship_dest_contact_email or None,

            "cargo_description":    order.biziship_cargo_desc or "",
            "special_instructions": order.biziship_special_instructions or "",
            "po_number":            order.biziship_po_number or "",
            "pickup_date":          pickup_date_str,

            # Summary Fields
            "weight":     order.biziship_total_weight,
            "weight_unit": order.biziship_total_weight_unit or "lbs",
            "num_pieces": sum(order.biziship_cargo_line_ids.mapped('pieces')),

            # Boolean Flags - Pickup
            "origin_residential":   order.biziship_origin_residential,
            "origin_liftgate":      order.biziship_origin_liftgate,
            "origin_limited_access": order.biziship_origin_limited_access,

            # Boolean Flags - Delivery
            "dest_appointment":     order.biziship_dest_appointment,
            "dest_residential":     order.biziship_dest_residential,
            "dest_notify":          order.biziship_dest_notify,
            "dest_limited_access":  order.biziship_dest_limited_access,
            "dest_liftgate":        order.biziship_dest_liftgate,
            "dest_hazmat":          order.biziship_dest_hazmat,

            # Accessorial Arrays
            "origin_more": order.biziship_origin_accessorial_ids.mapped('code'),
            "dest_more":   order.biziship_dest_accessorial_ids.mapped('code'),

            # Recurring weekly pickup / delivery hours (round-trips as plain keys)
            "origin_pickup_start":      _origin_hours.get('start'),
            "origin_pickup_end":        _origin_hours.get('end'),
            "origin_pickup_days":       _origin_hours.get('days'),
            "destination_pickup_start": _dest_hours.get('start'),
            "destination_pickup_end":   _dest_hours.get('end'),
            "destination_pickup_days":  _dest_hours.get('days'),

            # Stringified Cargo JSON - critical for web app compatibility
            "cargo_lines_json": json.dumps(cargo_lines)
        }


        erp_api_key = get_erp_api_key(self.env)
        base_url = api_utils.get_biziship_api_url(self.env)
        url = f"{base_url}/erp/saved-freights"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-ERP-API-Key": erp_api_key,
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
            "Content-Type": "application/json"
        }
        payload = {
            "name": self.name,
            "freightDetails": freight_details
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 201:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _("Freight saved successfully"),
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            elif response.status_code == 409:
                raise UserError(_("A saved freight named '%s' already exists. Please choose a different name.") % self.name)
            elif response.status_code == 403:
                raise UserError(_("You do not have a company associated with your BiziShip account."))
            elif response.status_code == 401:
                self.env.user.biziship_token = False
                raise UserError(_("Your BiziShip session has expired. Please reconnect in your User Profile."))
            else:
                raise UserError(_("Failed to save freight. Backend returned: %s") % response.text)
        except Exception as e:
            if isinstance(e, UserError):
                raise e
            raise UserError(_("Error connecting to BiziShip: %s") % str(e))
