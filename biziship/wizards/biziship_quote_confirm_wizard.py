import json
import re
import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.biziship import api_utils

# Shipment-notification CC email validation (mirrors the client-side regex).
BIZISHIP_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
BIZISHIP_CC_MAX = 10

_logger = logging.getLogger(__name__)

ACCESSORIAL_MAPPING = {
    "APPT": "Delivery Appointment",
    "LGDEL": "Lift Gate Delivery",
    "LGPU": "Lift Gate Pickup",
    "RESDEL": "Residential Delivery",
    "RESPU": "Residential Pickup",
    "INDEL": "Inside Delivery",
    "INPU": "Inside Pickup",
    "LTDDEL": "Limited Access Delivery",
    "LTDPU": "Limited Access Pickup",
    "NOTIFY": "Notify Consignee",
    "HAZM": "Hazardous Material",
    "SORTDEL": "Sort/Segregate Delivery",
    "SORTPU": "Sort/Segregate Pickup",
    "CONDEL": "Construction Site Delivery",
    "CONPU": "Construction Site Pickup",
    "PFZ": "Protection From Freezing",
    "CNVDEL": "Trade Show Delivery",
    "CNVPU": "Trade Show Pickup"
}

from odoo.addons.biziship.api_utils import get_biziship_api_url, get_erp_api_key, BIZISHIP_MODULE_VERSION, BIZISHIP_APP_NAME


class BizishipQuoteConfirmWizard(models.TransientModel):
    _name = 'biziship.quote.confirm.wizard'
    _description = 'Confirm BiziShip Quote'

    quote_id = fields.Many2one('biziship.quote', string="Selected Quote", required=True)
    sale_order_id = fields.Many2one(related="quote_id.sale_order_id", readonly=True)
    biziship_cargo_line_ids = fields.One2many(related="sale_order_id.biziship_cargo_line_ids", readonly=False)
    
    # Terminals
    origin_terminal_city = fields.Char(related="quote_id.origin_terminal_city", readonly=True)
    origin_terminal_state = fields.Char(related="quote_id.origin_terminal_state", readonly=True)
    origin_terminal_phone = fields.Char(related="quote_id.origin_terminal_phone", readonly=True)
    destination_terminal_city = fields.Char(related="quote_id.destination_terminal_city", readonly=True)
    destination_terminal_state = fields.Char(related="quote_id.destination_terminal_state", readonly=True)
    destination_terminal_phone = fields.Char(related="quote_id.destination_terminal_phone", readonly=True)
    
    # Pickup Date & Totals
    biziship_pickup_date = fields.Date(related="sale_order_id.biziship_pickup_date", readonly=True)
    biziship_total_weight = fields.Float(related="sale_order_id.biziship_total_weight", readonly=True)
    biziship_total_weight_unit = fields.Selection(related="sale_order_id.biziship_total_weight_unit", readonly=True)

    # Origin Details
    origin_company = fields.Char(related="sale_order_id.biziship_origin_company", readonly=True)
    origin_address = fields.Char(related="quote_id.origin_address", string="Origin Address", readonly=True)
    origin_address2 = fields.Char(related="quote_id.origin_address2", string="Origin Address 2", readonly=True)
    origin_city = fields.Char(related="sale_order_id.biziship_origin_city", string="Origin City", readonly=True)
    origin_state = fields.Char(related="sale_order_id.biziship_origin_state_id.code", string="Origin State", readonly=True)
    origin_zip = fields.Char(related="sale_order_id.biziship_origin_zip", string="Origin Zip", readonly=True)
    origin_phone = fields.Char(related="sale_order_id.company_id.phone", string="Origin Phone", readonly=True)
    
    origin_contact_name = fields.Char(string='Contact Name')
    origin_contact_phone = fields.Char(string='Contact Phone', required=True)
    origin_contact_email = fields.Char(string='Contact Email')
    
    # Destination Details
    destination_company = fields.Char(related="sale_order_id.biziship_dest_company", readonly=True)
    destination_address = fields.Char(related="quote_id.destination_address", string="Dest Address", readonly=True)
    destination_address2 = fields.Char(related="quote_id.destination_address2", string="Dest Address 2", readonly=True)
    destination_city = fields.Char(related="sale_order_id.biziship_dest_city", string="Dest City", readonly=True)
    destination_state = fields.Char(related="sale_order_id.biziship_dest_state_id.code", string="Dest State", readonly=True)
    destination_zip = fields.Char(related="sale_order_id.biziship_dest_zip", string="Dest Zip", readonly=True)
    destination_phone = fields.Char(related="sale_order_id.partner_shipping_id.phone", string="Dest Phone", readonly=True)
    
    destination_contact_name = fields.Char(string='Contact Name')
    destination_contact_phone = fields.Char(string='Contact Phone', required=True)
    destination_contact_email = fields.Char(string='Contact Email')

    # Quote Detailed Charges
    quote_details = fields.Text(related="quote_id.quote_details", readonly=True)

    carrier_name = fields.Char(related="quote_id.carrier_name", readonly=True)
    carrier_code = fields.Char(related="quote_id.carrier_code", readonly=True)
    total_charge = fields.Float(related="quote_id.total_charge", readonly=True)
    carrier_liability_new = fields.Float(related="quote_id.carrier_liability_new", readonly=True)
    carrier_liability_used = fields.Float(related="quote_id.carrier_liability_used", readonly=True)
    delivery_date = fields.Datetime(related="quote_id.delivery_date", readonly=True)
    currency = fields.Char(related="quote_id.currency", string="Currency Code", readonly=True)
    currency_id = fields.Many2one(related="quote_id.currency_id", readonly=True)
    quote_id_ref = fields.Char(related="quote_id.quote_id_ref", readonly=True)
    biziship_special_instructions = fields.Text(string="Special Instructions")
    # Sales Order reference — read-only display on the booking dialog (related, not stored).
    biziship_sales_order_name = fields.Char(related="sale_order_id.name", string="Sales Order", readonly=True)
    # Per-shipment extra notification recipients (editable chips), stored as a JSON array string.
    biziship_cc_emails_json = fields.Char(string="Shipment Notifications", default='[]')
    # Reference numbers (primary + additional) — carried from the quote, editable here.
    biziship_references_json = fields.Char(related="sale_order_id.biziship_references_json", readonly=False)
    # Salesperson notification — shown on the booking dialog, included by default, toggleable.
    biziship_salesperson_name = fields.Char(string="Salesperson", readonly=True)
    biziship_salesperson_email = fields.Char(string="Salesperson Email", readonly=True)
    biziship_notify_salesperson = fields.Boolean(string="Notify Salesperson", default=True)
    priority1_env = fields.Char(related="sale_order_id.biziship_priority1_env", readonly=True)
    po_number = fields.Char(string="PO Number", compute='_compute_po_number', store=True, readonly=False)

    carrier_logo = fields.Binary(related="quote_id.carrier_logo", string="Carrier Logo", readonly=True)


    accessorial_services_text = fields.Text(string="Accessorial Services", compute='_compute_accessorial_services')
    has_accessorials = fields.Boolean(compute='_compute_accessorial_services')

    is_hazmat = fields.Boolean(compute='_compute_is_hazmat')
    hazmat_contact_name = fields.Char(string='Contact Name')
    hazmat_contact_phone = fields.Char(string='Contact Phone')
    hazmat_un_number = fields.Char(string='UN Number')
    hazmat_proper_shipping_name = fields.Char(string='Proper Shipping Name')
    hazmat_hazard_class = fields.Selection([
        ('1', '1'), ('1.1', '1.1'), ('1.2', '1.2'), ('1.3', '1.3'), ('1.3C', '1.3C'), ('1.4', '1.4'), ('1.4C', '1.4C'), ('1.4G', '1.4G'), ('1.4S', '1.4S'), ('1.5', '1.5'), ('1.6', '1.6'), ('2', '2'), ('2.1', '2.1'), ('2.2', '2.2'), ('2.2(5.1)', '2.2(5.1)'), ('2.2(6.1)', '2.2(6.1)'), ('2.3', '2.3'), ('2.3(8)', '2.3(8)'), ('3', '3'), ('3(6.1)', '3(6.1)'), ('3(6.1;8)', '3(6.1;8)'), ('3(8)', '3(8)'), ('4', '4'), ('4.1', '4.1'), ('4.2', '4.2'), ('4.3', '4.3'), ('4.3(6.1)', '4.3(6.1)'), ('5', '5'), ('5.1', '5.1'), ('5.1(6.1,8)', '5.1(6.1,8)'), ('5.1(6.1)', '5.1(6.1)'), ('5.1(8)', '5.1(8)'), ('5.2', '5.2'), ('5.2(8)', '5.2(8)'), ('6', '6'), ('6.1', '6.1'), ('6.1(3)', '6.1(3)'), ('6.1(8,3)', '6.1(8,3)'), ('6.1(8)', '6.1(8)'), ('6.2', '6.2'), ('7', '7'), ('7(2.2)', '7(2.2)'), ('8', '8'), ('8(3)', '8(3)'), ('8(5.1)', '8(5.1)'), ('8(6.1)', '8(6.1)'), ('9', '9'), ('NA', 'NA')
    ], string='Hazard Class')
    hazmat_packing_group = fields.Selection([
        ('I', 'I'), ('II', 'II'), ('III', 'III'), ('NA', 'NA')
    ], string='Packing Group')
    hazmat_pieces_packaging = fields.Selection([
        ('Bag', 'Bag'), ('Bale', 'Bale'), ('Box', 'Box'), ('Bucket', 'Bucket'), ('Bundle', 'Bundle'), ('Can', 'Can'), ('Carton', 'Carton'), ('Case', 'Case'), ('Coil', 'Coil'), ('Crate', 'Crate'), ('Cylinder', 'Cylinder'), ('Drums', 'Drums'), ('Pail', 'Pail'), ('Pieces', 'Pieces'), ('Pallet', 'Pallet'), ('Reel', 'Reel'), ('Roll', 'Roll'), ('Skid', 'Skid'), ('Tube', 'Tube'), ('Tote', 'Tote')
    ], string='Pieces Packaging')

    is_hazmat_valid = fields.Boolean(compute='_compute_is_hazmat_valid')

    @api.model
    def default_get(self, fields_list):
        res = super(BizishipQuoteConfirmWizard, self).default_get(fields_list)
        if 'quote_id' in res:
            quote = self.env['biziship.quote'].browse(res['quote_id'])
            so = quote.sale_order_id
            if so:
                res.update({
                    'origin_contact_name': so.biziship_origin_contact_name,
                    'origin_contact_phone': so.biziship_origin_contact_phone,
                    'origin_contact_email': so.biziship_origin_contact_email,
                    'destination_contact_name': so.biziship_dest_contact_name,
                    'destination_contact_phone': so.biziship_dest_contact_phone,
                    'destination_contact_email': so.biziship_dest_contact_email,
                    # Show the merged schedule prefix + user text so the booking dialog
                    # displays the pickup/delivery hours that will be sent.
                    'biziship_special_instructions': so._biziship_merge_schedule_instructions(so.biziship_special_instructions),
                })
                # Salesperson notification recipient — included by default when they have an email.
                salesperson = so.user_id
                if salesperson:
                    res['biziship_salesperson_name'] = salesperson.name or ''
                    res['biziship_salesperson_email'] = salesperson.email or ''
                    res['biziship_notify_salesperson'] = bool(salesperson.email)
        return res

    @api.model
    def biziship_get_default_cc_emails(self):
        """Fetch the company's default notification recipients from the ERP Gateway.

        Caller-company scoping is handled server-side via X-User-Email; we never pass
        a company id. Always returns a list — on any error/timeout, returns [] so the
        booking dialog is never blocked.
        """
        try:
            base_url = get_biziship_api_url(self.env).rstrip('/')
            user = self.env.user
            headers = {
                "X-ERP-API-Key": get_erp_api_key(self.env),
                "X-User-Email": (user.biziship_email if user.biziship_token and user.biziship_email else user.email) or "",
            }
            resp = requests.get(
                f"{base_url}/erp/company/default-copy-to-emails",
                headers=headers,
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()
            emails = data.get('defaultCopyToEmails') or []
            return [e for e in emails if isinstance(e, str)]
        except Exception as e:
            _logger.warning("BiziShip: failed to fetch default CC emails: %s", str(e))
            return []

    def _biziship_clean_cc_emails(self):
        """Parse, trim, validate, dedupe (case-insensitive) and cap the editable CC chips.

        Raises UserError on an invalid entry or when the cap is exceeded. Returns a list.
        """
        self.ensure_one()
        try:
            raw = json.loads(self.biziship_cc_emails_json or '[]')
        except (ValueError, TypeError):
            raw = []
        if not isinstance(raw, list):
            raw = []
        cleaned = []
        seen = set()
        for item in raw:
            email = (item or '').strip() if isinstance(item, str) else ''
            if not email:
                continue
            if not BIZISHIP_EMAIL_RE.match(email):
                raise UserError(_('"%s" is not a valid email address.') % email)
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(email)
        if len(cleaned) > BIZISHIP_CC_MAX:
            raise UserError(_("Maximum %s notification addresses allowed.") % BIZISHIP_CC_MAX)
        return cleaned

    @api.depends('is_hazmat', 'hazmat_contact_name', 'hazmat_contact_phone', 'hazmat_un_number', 'hazmat_proper_shipping_name', 'hazmat_hazard_class', 'hazmat_packing_group', 'hazmat_pieces_packaging')
    def _compute_is_hazmat_valid(self):
        for rec in self:
            if not rec.is_hazmat:
                rec.is_hazmat_valid = True
            else:
                rec.is_hazmat_valid = bool(
                    rec.hazmat_contact_name and
                    rec.hazmat_contact_phone and
                    rec.hazmat_un_number and
                    rec.hazmat_proper_shipping_name and
                    rec.hazmat_hazard_class and
                    rec.hazmat_packing_group and
                    rec.hazmat_pieces_packaging
                )

    @api.depends('quote_id.sale_order_id.biziship_extracted_json')
    def _compute_is_hazmat(self):
        for rec in self:
            is_hazmat = False
            if rec.quote_id and rec.quote_id.sale_order_id and rec.quote_id.sale_order_id.biziship_extracted_json:
                try:
                    data = json.loads(rec.quote_id.sale_order_id.biziship_extracted_json)
                    codes = data.get('accessorial_codes', [])
                    if 'HAZM' in codes:
                        is_hazmat = True
                except Exception:
                    pass
            rec.is_hazmat = is_hazmat

    @api.depends('quote_id.sale_order_id.biziship_po_number', 'quote_id.sale_order_id.biziship_extracted_json')
    def _compute_po_number(self):
        for rec in self:
            po = False
            if rec.quote_id and rec.quote_id.sale_order_id:
                so = rec.quote_id.sale_order_id
                po = so.biziship_po_number

                # Fallback to HexcelPack's Destination PO field
                if not po:
                    po = getattr(so, 'x_destination_po', False) or False

                # Fallback to extracted JSON if still empty
                if not po and so.biziship_extracted_json:
                    try:
                        data = json.loads(so.biziship_extracted_json)
                        po = data.get('po_number', False)
                    except Exception:
                        pass
            rec.po_number = po

    @api.depends('quote_id.sale_order_id.biziship_extracted_json')
    def _compute_accessorial_services(self):
        for rec in self:
            services_text = ""
            has_acc = False
            if rec.quote_id and rec.quote_id.sale_order_id and rec.quote_id.sale_order_id.biziship_extracted_json:
                try:
                    data = json.loads(rec.quote_id.sale_order_id.biziship_extracted_json)
                    codes = data.get('accessorial_codes', [])
                    if codes:
                        labels = [ACCESSORIAL_MAPPING.get(code, code) for code in codes]
                        services_text = "\n".join(f"• {label}" for label in labels)
                        has_acc = True
                except Exception:
                    pass
            rec.accessorial_services_text = services_text
            rec.has_accessorials = has_acc


    def action_confirm_and_send(self):
        self.ensure_one()
        
        if not self.po_number:
            raise UserError(_("Please provide a PO Number before submitting the quote."))
            
        email2quote_api_url = get_biziship_api_url(self.env)
        erp_api_key = get_erp_api_key(self.env)
        
        local_api_book_url = f"{email2quote_api_url.rstrip('/')}/erp/book"
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "Content-Type": "application/json",
            "X-User-Email": (self.env.user.biziship_email if self.env.user.biziship_token and self.env.user.biziship_email else self.env.user.email) or "",
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
        }
        
        sale_order = self.quote_id.sale_order_id
        
        # Save the confirmed PO Number back to the Sale Order if it was modified here
        if sale_order.biziship_po_number != self.po_number:
            sale_order.biziship_po_number = self.po_number
        
        
        extracted_data = {}
        if sale_order.biziship_extracted_json:
            try:
                extracted_data = json.loads(sale_order.biziship_extracted_json)
            except Exception:
                pass
                
        import re
        def format_phone(phone_str):
            if not phone_str:
                return None
            digits = re.sub(r'\D', '', phone_str)
            if len(digits) >= 10:
                return digits[-10:]
            return None

        company = self.env.company
        shipper = {
            "company_name": sale_order.biziship_origin_company or extracted_data.get("origin_company") or company.name,
            "address_line1": sale_order.biziship_origin_address or extracted_data.get("origin_address") or company.street or "",
            "address_line2": sale_order.biziship_origin_address2 or extracted_data.get("origin_address2") or company.street2 or "",
            "city": sale_order.biziship_origin_city or extracted_data.get("origin_city") or company.city or "",
            "state": sale_order.biziship_origin_state_id.code if sale_order.biziship_origin_state_id else (extracted_data.get("origin_state") or (company.state_id.code if company.state_id else "")),
            "zip": sale_order.biziship_origin_zip or extracted_data.get("origin_zip") or company.zip or "",
        }
        # Update contact fields in payload from wizard
        if self.origin_contact_name:
            shipper["contact_name"] = self.origin_contact_name
            shipper["contact"] = self.origin_contact_name
        
        origin_phone = format_phone(self.origin_contact_phone)
        if origin_phone:
            shipper["phone"] = origin_phone
            
        if self.origin_contact_email:
            shipper["email"] = self.origin_contact_email

        partner = sale_order.partner_shipping_id or sale_order.partner_id
        consignee = {
            "company_name": sale_order.biziship_dest_company or extracted_data.get("destination_company") or partner.name,
            "address_line1": sale_order.biziship_dest_address or extracted_data.get("destination_address") or partner.street or "",
            "address_line2": sale_order.biziship_dest_address2 or extracted_data.get("destination_address2") or partner.street2 or "",
            "city": sale_order.biziship_dest_city or extracted_data.get("destination_city") or partner.city or "",
            "state": sale_order.biziship_dest_state_id.code if sale_order.biziship_dest_state_id else (extracted_data.get("destination_state") or (partner.state_id.code if partner.state_id else "")),
            "zip": sale_order.biziship_dest_zip or extracted_data.get("destination_zip") or partner.zip or "",
        }

        if self.destination_contact_name:
            consignee["contact_name"] = self.destination_contact_name
            consignee["contact"] = self.destination_contact_name
            
        dest_phone = format_phone(self.destination_contact_phone)
        if dest_phone:
            consignee["phone"] = dest_phone
            
        if self.destination_contact_email:
            consignee["email"] = self.destination_contact_email
        
        # Save back to Sale Order
        sale_order.write({
            'biziship_origin_contact_name': self.origin_contact_name,
            'biziship_origin_contact_phone': self.origin_contact_phone,
            'biziship_origin_contact_email': self.origin_contact_email,
            'biziship_dest_contact_name': self.destination_contact_name,
            'biziship_dest_contact_phone': self.destination_contact_phone,
            'biziship_dest_contact_email': self.destination_contact_email,
        })
        
        from datetime import timedelta
        
        today = fields.Date.context_today(self)
        tomorrow = today + timedelta(days=1)
        pickup_date = extracted_data.get("pickup_date")
        if not pickup_date or str(pickup_date) < str(today):
            pickup_date = str(tomorrow)
            
        # Build line items for booking
        line_items = []
        for line in self.biziship_cargo_line_ids:
            line_item = {
                "num_pieces": line.pieces or 1,
                "total_pieces": 1,
                "packaging_type": line.packaging_type or "pallet",
                "weight": round(api_utils.convert_to_lbs(line.weight, line.weight_unit) * (line.pieces or 1), 2),
                "weight_unit": "lbs",
                "length": round(api_utils.convert_to_inches(line.length, line.dim_unit), 2),
                "width": round(api_utils.convert_to_inches(line.width, line.dim_unit), 2),
                "height": round(api_utils.convert_to_inches(line.height, line.dim_unit), 2),
                "dimension_unit": "inches",
                "freight_class": line.freight_class or line.computed_freight_class or "50",
                "cargo_description": line.cargo_desc or "General Freight",
                "hazmat": line.hazmat or False,
                "stackable": line.stackable or False
            }
            if line.nmfc:
                line_item["nmfc_code"] = line.nmfc
            line_items.append(line_item)

        payload = {
            "quote_id": self.quote_id_ref,
            "po_number": self.po_number or "",
            "shipper": shipper,
            "consignee": consignee,
            "pickup_date": pickup_date,
            # Already merged (and possibly edited) in the booking dialog — send verbatim.
            "pickup_note": self.biziship_special_instructions or "",
            "line_items": line_items
        }

        # Sales Order reference (additive — single string, omitted when empty). The Odoo
        # sale order's own name is the authoritative Sales Order number.
        sales_order_ref = (sale_order.name or '').strip() if sale_order else ''
        if sales_order_ref:
            payload["sales_order"] = sales_order_ref

        # Reference numbers: first entry = primary reference_number, the rest =
        # additional_references. Trim, drop empties; omit either field entirely when empty.
        try:
            _refs = json.loads(self.biziship_references_json or '[]')
        except (ValueError, TypeError):
            _refs = []
        _refs = [(r or '').strip() for r in _refs if isinstance(r, str)]
        if _refs and _refs[0]:
            payload["reference_number"] = _refs[0][:64]
        _additional = [r for r in _refs[1:] if r]
        if _additional:
            payload["additional_references"] = _additional

        # Per-shipment extra notification recipients. The backend unions these with the
        # company defaults. Include the salesperson (unless excluded via the dialog toggle).
        # Read the salesperson email straight from the order — the wizard's readonly
        # salesperson_email field is display-only and is NOT persisted on web_save.
        cc_emails = self._biziship_clean_cc_emails()
        sp_email = ''
        if self.biziship_notify_salesperson and sale_order and sale_order.user_id:
            sp_email = (sale_order.user_id.email or '').strip()
            if sp_email and BIZISHIP_EMAIL_RE.match(sp_email) and sp_email.lower() not in {e.lower() for e in cc_emails}:
                cc_emails.append(sp_email)
        _logger.info(
            "BiziShip cc_emails → editable_json=%r | notify_salesperson=%r | sp_email=%r | final=%r",
            self.biziship_cc_emails_json, self.biziship_notify_salesperson, sp_email, cc_emails,
        )
        # Only include the field when there is at least one extra recipient.
        if cc_emails:
            payload["cc_emails"] = cc_emails

        if self.is_hazmat:
            if not all([self.hazmat_contact_name, self.hazmat_contact_phone, self.hazmat_un_number, self.hazmat_proper_shipping_name, self.hazmat_hazard_class, self.hazmat_packing_group, self.hazmat_pieces_packaging]):
                raise UserError(_("All Hazardous Material Details fields are required."))
                
            payload["hazmat_contact_name"] = self.hazmat_contact_name
            payload["hazmat_contact_phone"] = self.hazmat_contact_phone
            payload["hazmat_detail"] = {
                "identificationNumber": self.hazmat_un_number,
                "properShippingName": self.hazmat_proper_shipping_name,
                "hazardClass": self.hazmat_hazard_class,
                "packingGroup": self.hazmat_packing_group,
                "piecesPackagingType": self.hazmat_pieces_packaging
            }

        _logger.info("BiziShip Booking API Request Headers: %s", headers)
        _logger.info("BiziShip Booking API Request Payload: %s", json.dumps(payload, indent=2))

        try:
            response = requests.post(
                local_api_book_url, 
                headers=headers, 
                json=payload, 
                timeout=45
            )
            if not response.ok:
                try:
                    error_json = response.json()
                    if 'errors' in error_json and isinstance(error_json['errors'], list) and len(error_json['errors']) > 0:
                        error_msg = error_json['errors'][0]
                    else:
                        error_msg = error_json.get('detail', response.text)
                except Exception:
                    error_msg = response.text
                raise UserError(_("%s") % error_msg)
                
            response_json = response.json()
            sale_order.write({
                'biziship_bol_number': response_json.get('bol_number'),
                'biziship_shipment_id': response_json.get('shipment_id'),
                'biziship_booking_id': response_json.get('biziship_id') or False,
                'biziship_bol_url': response_json.get('bol_url'),
                'biziship_documents_json': json.dumps(response_json.get('documents', [])) if response_json.get('documents') else False
            })

            # Fetch fresh documents list and PRO number from the documents endpoint
            try:
                sale_order.action_biziship_refresh_documents()
            except Exception as e:
                _logger.warning("Failed to fetch shipment documents after booking: %s", str(e))

            # Parse reference fields from the booked BOL PDF
            bol_url = response_json.get('bol_url')
            if bol_url:
                ref_fields = self._parse_bol_reference(bol_url)
                if ref_fields:
                    sale_order.write(ref_fields)

        except requests.exceptions.RequestException as e:
            error_details = e.response.text if hasattr(e, 'response') and e.response is not None else str(e)
            raise UserError(_("Failed to contact Email2Quote booking API.\n\nDetails:\n%s") % error_details)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'views': [(False, 'form')],
            'target': 'main',
            'context': {
                'active_id': sale_order.id,
                'default_active_tab': 'ltl_freight_quotes',
                'biziship_booking_success': True,
            },
        }

    def _parse_bol_reference(self, bol_url):
        """Download BOL PDF from bol_url and POST to /erp/bol/reference to extract the Reference section."""
        try:
            pdf_resp = requests.get(bol_url, timeout=30)
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
        except Exception as e:
            _logger.warning("Failed to download BOL PDF from %s: %s", bol_url, str(e))
            return {}

        try:
            base_url = get_biziship_api_url(self.env).rstrip('/')
            erp_api_key = get_erp_api_key(self.env)
            headers = {
                "X-ERP-API-Key": erp_api_key,
                "X-User-Email": (
                    self.env.user.biziship_email
                    if self.env.user.biziship_token and self.env.user.biziship_email
                    else self.env.user.email
                ) or "",
            }
            resp = requests.post(
                f"{base_url}/erp/bol/reference",
                headers=headers,
                files={"file": ("bol.pdf", pdf_bytes, "application/pdf")},
                timeout=45,
            )
            resp.raise_for_status()
            response_json = resp.json()
            _logger.info("BOL reference API response: %s", response_json)

            result = {'biziship_ref_json': json.dumps(response_json)}

            # Also populate the PRO number field if present in the fields array
            for f in response_json.get('fields', []):
                if f.get('label', '').lower() in ('itemized pro', 'pro', 'pro number'):
                    result['biziship_pro_number'] = f.get('value') or False
                    break

            return result
        except Exception as e:
            _logger.warning("BOL reference API call failed: %s", str(e))
            return {}
