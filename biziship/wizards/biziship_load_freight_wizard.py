import re
import requests
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

from odoo.addons.biziship import api_utils
from odoo.addons.biziship.api_utils import get_erp_api_key, BIZISHIP_APP_NAME, BIZISHIP_MODULE_VERSION

class BizishipLoadFreightFilterUser(models.TransientModel):
    _name = 'biziship.load.freight.filter.user'
    _description = 'Load Saved Freight Filter User'
    wizard_id = fields.Many2one('biziship.load.freight.wizard')
    name = fields.Char()

class BizishipLoadFreightWizard(models.TransientModel):
    _name = 'biziship.load.freight.wizard'
    _description = 'Load Saved Freight'

    freight_line_ids = fields.One2many('biziship.load.freight.line', 'wizard_id', string='Saved Freights')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    
    # Search & Filter Fields
    search_name = fields.Char(string='Search freight name...')
    filter_user_ids = fields.One2many('biziship.load.freight.filter.user', 'wizard_id')
    filter_user_id = fields.Many2one('biziship.load.freight.filter.user', string='Filter by person', domain="[('wizard_id', '=', id)]")
    raw_freights_json = fields.Text(string='Raw Data Cache')
    status_message = fields.Char(string='Status', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        return res

    def _populate_freights(self):
        self.ensure_one()
        token = self.env.user.biziship_token
        if not token:
            self.status_message = "Please connect your BiziShip account in the User settings."
            return
        erp_api_key = get_erp_api_key(self.env)
        base_url = api_utils.get_biziship_api_url(self.env)
        url = f"{base_url}/erp/saved-freights"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-ERP-API-Key": erp_api_key,
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
        }
        _logger.info("BiziShip: Fetching freights from %s", url)
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                freights = response.json()
                _logger.info("BiziShip: Fetched %d freights for wizard", len(freights))
                
                if not freights:
                    self.status_message = "Your freight pool is currently empty. Save a freight first!"
                    self.raw_freights_json = json.dumps([])
                else:
                    self.status_message = ""
                    self.raw_freights_json = json.dumps(freights)
                
                # Extract unique users for the filter dropdown
                user_names = list(set([f.get('createdBy', {}).get('fullName', 'Unknown User') for f in freights if f.get('createdBy', {}).get('fullName')]))
                user_names.sort()
                
                # Clean old filter users and create new ones for this wizard instance
                self.filter_user_ids.unlink()
                self.env['biziship.load.freight.filter.user'].create([{'name': name, 'wizard_id': self.id} for name in user_names])
                
                self._apply_filters()
            elif response.status_code == 403:
                _logger.error("BiziShip: Company registration error. Detail: %s", response.text)
                try:
                    detail = response.json().get('detail', 'No company associated with your account.')
                    self.status_message = detail
                except:
                    self.status_message = "No company associated with your BiziShip account. Please complete registration in your BiziShip profile."
            else:
                _logger.error("BiziShip: Failed to fetch freights. Status: %d, Response: %s", response.status_code, response.text)
                self.status_message = f"Failed to fetch freights (Error {response.status_code})"
        except Exception as e:
            _logger.exception("BiziShip: Error fetching freights for wizard")
            self.status_message = f"Unable to connect to BiziShip: {str(e)}"

    @api.onchange('search_name', 'filter_user_id')
    def _onchange_filters(self):
        self._apply_filters()

    def _apply_filters(self):
        self.ensure_one()
        json_data = self.raw_freights_json
        if not json_data:
            return
            
        try:
            freights = json.loads(json_data)
        except Exception as e:
            _logger.error("BiziShip: Error parsing freight JSON: %s", str(e))
            return

        search = (self.search_name or '').lower()
        user_name_filter = self.filter_user_id.name if self.filter_user_id else None
        
        lines = []
        for f in freights:
            name = f.get('name', '') or 'Unnamed Freight'
            created_by = f.get('createdBy', {}).get('fullName', 'Unknown User')
            
            # Apply Filter 1: Name Search
            if search and search not in name.lower():
                continue
                
            # Apply Filter 2: User Filter
            if user_name_filter and user_name_filter != created_by:
                continue

            details = f.get('freightDetails', {})
            origin_zip = details.get('origin_zip', '-----')
            dest_zip = details.get('dest_zip', '-----')
            
            # 1. Total Weight & Cargo Count
            cargo_lines = details.get('line_items', [])
            if not cargo_lines and details.get('cargo_lines_json'):
                try:
                    cargo_lines = json.loads(details['cargo_lines_json'])
                except:
                    cargo_lines = []
            
            weight = details.get('weight', 0)
            if (not weight or weight == 0) and cargo_lines:
                weight = sum(item.get('weight', 0) for item in cargo_lines) or 0
            
            weight_unit = (details.get('weight_unit') or 'lbs').lower()
            cargo_count = len(cargo_lines) or 1
            
            origin_info = f"{origin_zip} → {dest_zip}"
            summary_info = f"{int(weight)} {weight_unit} • {cargo_count} cargo line{'s' if cargo_count > 1 else ''}"
            
            created_at_raw = f.get('createdAt', '')
            date_str = created_at_raw.replace('T', ' ')[:16] if created_at_raw else "Recently"
            creator_info = f"{created_by} • Saved {date_str}"

            lines.append((0, 0, {
                'freight_id': str(f.get('id', '')),
                'name': name,
                'origin_info': origin_info,
                'summary_info': summary_info,
                'creator_info': creator_info,
            }))
        
        _logger.info("BiziShip: Filter applied. Results: %d", len(lines))
        
        # In Odoo 17 onchange, 'self' is virtual. To make 'Launch' buttons work (standard Odoo actions),
        # we need REAL database records with REAL IDs. We force this by writing to self._origin.
        target = self._origin if self._origin else self
        
        # 1. Clear existing real lines from DB
        if target.id:
            self.env['biziship.load.freight.line'].sudo().search([('wizard_id', '=', target.id)]).unlink()
        
        # 2. Create new real lines in DB
        new_lines = []
        for line_vals in lines:
            # line_vals[2] contains the dictionary of values
            res = self.env['biziship.load.freight.line'].sudo().create({
                **line_vals[2],
                'wizard_id': target.id
            })
            new_lines.append(res.id)
            
        # 3. Synchronize the virtual field so the UI refreshes
        self.freight_line_ids = [(6, 0, new_lines)]

    def action_load_freight_from_id(self, freight_id):
        """Helper to load a specific freight ID into the order"""
        token = self.env.user.biziship_token
        if not token:
            raise UserError(_("Please connect your BiziShip account first."))
        erp_api_key = get_erp_api_key(self.env)
        base_url = api_utils.get_biziship_api_url(self.env)
        url = f"{base_url}/erp/saved-freights"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-ERP-API-Key": erp_api_key,
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 401:
                self.env.user.biziship_token = False
                raise UserError(_("Your BiziShip session has expired. Please reconnect in your User Profile."))
            elif response.status_code != 200:
                raise UserError(_("Failed to fetch freight details."))
            
            freights = response.json()
            selected_freight = next((f for f in freights if f['id'] == freight_id), None)
            
            if not selected_freight or 'freightDetails' not in selected_freight:
                raise UserError(_("Selected freight details not found."))
            
            details = selected_freight['freightDetails']
            _logger.info("BiziShip: Loading Freight Details - %s", json.dumps(details, indent=2))
            order = self.sale_order_id

            def get_val(key, default=''):
                if key not in details:
                    return default
                val = details.get(key)
                return val if val is not None else default

            # 1. Update Sale Order Fields
            pickup_date = details.get('pickup_date') or str(fields.Date.today())
            if pickup_date < str(fields.Date.today()):
                pickup_date = str(fields.Date.today())

            vals = {
                'biziship_pickup_date': pickup_date,
                'biziship_origin_company': get_val('origin_company'),
                'biziship_origin_address': get_val('origin_address'),
                'biziship_origin_address2': get_val('origin_address2'),
                'biziship_origin_city': get_val('origin_city'),
                'biziship_origin_zip': get_val('origin_zip'),
                'biziship_cargo_desc': get_val('cargo_description', 'General Freight'),
                'biziship_special_instructions': get_val('special_instructions'),
                'biziship_po_number': get_val('po_number'),
                'biziship_total_weight_unit': (get_val('weight_unit', 'lbs')).lower()[:3],
                
                # Contact fields — check new names first, then legacy
                'biziship_origin_contact_name': details.get('origin_contact_name') or '',
                'biziship_origin_contact_phone': details.get('origin_contact_phone') or details.get('origin_phone') or '',
                'biziship_origin_contact_email': details.get('origin_contact_email') or details.get('origin_email') or '',
                'biziship_dest_contact_name': details.get('dest_contact_name') or details.get('destination_contact_name') or '',
                'biziship_dest_contact_phone': details.get('dest_contact_phone') or details.get('destination_phone') or '',
                'biziship_dest_contact_email': details.get('dest_contact_email') or details.get('destination_email') or '',
                
                # Boolean Flags - Pickup
                'biziship_origin_residential': details.get('origin_residential', False),
                'biziship_origin_liftgate': details.get('origin_liftgate', False),
                'biziship_origin_limited_access': details.get('origin_limited_access', False),
                
                # Boolean Flags - Delivery
                'biziship_dest_appointment': details.get('dest_appointment', False),
                'biziship_dest_residential': details.get('dest_residential', False),
                'biziship_dest_notify': details.get('dest_notify', False),
                'biziship_dest_limited_access': details.get('dest_limited_access', False),
                'biziship_dest_liftgate': details.get('dest_liftgate', False),
                'biziship_dest_hazmat': details.get('dest_hazmat', False),
                
                # New individual Destination fields or fallback to old names
                'biziship_dest_city': details.get('destination_city') or details.get('dest_city') or '',
            }
            
            # 1. Update Country IDs first (needed for state lookup)
            origin_country = self.env['res.country'].search([('code', '=', details.get('origin_country', 'US'))], limit=1)
            dest_country_code = details.get('destination_country') or details.get('dest_country') or 'US'
            dest_country = self.env['res.country'].search([('code', '=', dest_country_code)], limit=1)
            
            vals = {
                'biziship_pickup_date': pickup_date,
                'biziship_origin_company': get_val('origin_company'),
                'biziship_origin_address': get_val('origin_address'),
                'biziship_origin_address2': get_val('origin_address2'),
                'biziship_origin_city': get_val('origin_city'),
                'biziship_origin_zip': re.sub(r'\D', '', get_val('origin_zip') or '')[:5],
                'biziship_origin_country_id': origin_country.id if origin_country else False,
                
                'biziship_cargo_desc': get_val('cargo_description', 'General Freight'),
                'biziship_special_instructions': get_val('special_instructions'),
                'biziship_po_number': get_val('po_number'),
                'biziship_total_weight_unit': (get_val('weight_unit', 'lbs')).lower()[:3],
                
                # Contact fields — check new names first, then legacy
                'biziship_origin_contact_name': details.get('origin_contact_name') or '',
                'biziship_origin_contact_phone': details.get('origin_contact_phone') or details.get('origin_phone') or '',
                'biziship_origin_contact_email': details.get('origin_contact_email') or details.get('origin_email') or '',
                'biziship_dest_contact_name': details.get('dest_contact_name') or details.get('destination_contact_name') or '',
                'biziship_dest_contact_phone': details.get('dest_contact_phone') or details.get('destination_phone') or '',
                'biziship_dest_contact_email': details.get('dest_contact_email') or details.get('destination_email') or '',

                # Boolean Flags - Pickup
                'biziship_origin_residential': details.get('origin_residential', False),
                'biziship_origin_liftgate': details.get('origin_liftgate', False),
                'biziship_origin_limited_access': details.get('origin_limited_access', False),
                
                # Boolean Flags - Delivery
                'biziship_dest_appointment': details.get('dest_appointment', False),
                'biziship_dest_residential': details.get('dest_residential', False),
                'biziship_dest_notify': details.get('dest_notify', False),
                'biziship_dest_limited_access': details.get('dest_limited_access', False),
                'biziship_dest_liftgate': details.get('dest_liftgate', False),
                'biziship_dest_hazmat': details.get('dest_hazmat', False),
                
                'biziship_dest_city': details.get('destination_city') or details.get('dest_city') or '',
                'biziship_dest_country_id': dest_country.id if dest_country else False,
            }
            
            # 2. State Mapping (Scoped by Country ID to avoid 'GA' -> Goa issues)
            origin_state_code = details.get('origin_state')
            if origin_state_code and origin_country:
                state = self.env['res.country.state'].search([
                    ('code', '=', origin_state_code), 
                    ('country_id', '=', origin_country.id)
                ], limit=1)
                if state: vals['biziship_origin_state_id'] = state.id

            dest_state_code = details.get('destination_state') or details.get('dest_state')
            if dest_state_code and dest_country:
                state = self.env['res.country.state'].search([
                    ('code', '=', dest_state_code), 
                    ('country_id', '=', dest_country.id)
                ], limit=1)
                if state: vals['biziship_dest_state_id'] = state.id

            # Destination Address Info (Handling both 'destination_' and 'dest_' prefixes)
            if 'destination_company' in details: vals['biziship_dest_company'] = details['destination_company']
            elif 'dest_company' in details: vals['biziship_dest_company'] = details['dest_company']
            
            if 'destination_address' in details: vals['biziship_dest_address'] = details['destination_address']
            elif 'dest_address' in details: vals['biziship_dest_address'] = details['dest_address']
            
            if 'destination_address2' in details: vals['biziship_dest_address2'] = details['destination_address2']
            elif 'dest_address2' in details: vals['biziship_dest_address2'] = details['dest_address2']
            
            if 'destination_zip' in details: vals['biziship_dest_zip'] = re.sub(r'\D', '', details['destination_zip'] or '')[:5]
            elif 'dest_zip' in details: vals['biziship_dest_zip'] = re.sub(r'\D', '', details['dest_zip'] or '')[:5]

            # Extended Accessorials Mapping
            # We handle 'accessorial_codes' (new spec) or 'origin_more'/'dest_more' (old spec/parallel)
            all_codes = details.get('accessorial_codes', [])
            if not isinstance(all_codes, list): all_codes = []
            
            origin_more = details.get('origin_more', [])
            if not isinstance(origin_more, list): origin_more = []
            
            dest_more = details.get('dest_more', [])
            if not isinstance(dest_more, list): dest_more = []
            
            # Combine all for selection from DB
            lookup_codes = list(set(all_codes + origin_more + dest_more))
            
            accs_origin = self.env['biziship.accessorial'].search([('code', 'in', lookup_codes), ('type', '=', 'origin')])
            vals['biziship_origin_accessorial_ids'] = [(6, 0, accs_origin.ids)]

            accs_dest = self.env['biziship.accessorial'].search([('code', 'in', lookup_codes), ('type', '=', 'destination')])
            vals['biziship_dest_accessorial_ids'] = [(6, 0, accs_dest.ids)]

            # Recurring weekly hours — rebuild the JSON fields from saved keys,
            # falling back to defaults so older templates without them still load.
            def _build_hours(start_key, end_key, days_key):
                start = details.get(start_key) or '08:00'
                end = details.get(end_key) or '17:00'
                days = details.get(days_key)
                if not isinstance(days, list) or not days:
                    days = ['MON', 'TUE', 'WED', 'THU', 'FRI']
                return json.dumps({'start': start, 'end': end, 'days': days})

            vals['biziship_origin_pickup_hours'] = _build_hours(
                'origin_pickup_start', 'origin_pickup_end', 'origin_pickup_days')
            vals['biziship_dest_delivery_hours'] = _build_hours(
                'destination_pickup_start', 'destination_pickup_end', 'destination_pickup_days')

            _logger.info("BiziShip: Values to write to Order: %s", json.dumps(vals, indent=2))
            order.write(vals)

            # 2. Cargo Mapping Helpers
            def normalize_pkg(pkg):
                if not pkg: return 'pallet'
                pkg = pkg.lower()
                if 'pallet' in pkg: return 'pallet'
                if 'crate' in pkg: return 'crate'
                if 'box' in pkg: return 'box'
                if 'drum' in pkg: return 'drum'
                return 'pallet'

            def normalize_dim_unit(unit):
                if not unit: return 'in'
                unit = unit.lower()
                if 'inch' in unit or unit == 'in': return 'in'
                if 'cm' in unit: return 'cm'
                if 'm' in unit: return 'm'
                if 'ft' in unit: return 'ft'
                return 'in'

            # 3. Handle Cargo Lines (Support JSON string if list is missing)
            order.biziship_cargo_line_ids.unlink()
            line_items = details.get('line_items')
            if not line_items and details.get('cargo_lines_json'):
                try:
                    line_items = json.loads(details['cargo_lines_json'])
                except:
                    line_items = []
            
            if not line_items:
                # Fallback to top-level fields
                line_items = [{
                    'num_pieces': details.get('num_pieces', 1),
                    'weight': details.get('weight', 0),
                    'length': details.get('length', 48),
                    'width': details.get('width', 40),
                    'height': details.get('height', 48),
                    'packaging_type': details.get('packaging_type', 'pallet'),
                    'freight_class': details.get('freight_class', '70'),
                    'cargo_description': details.get('cargo_description', ''),
                    'dimension_unit': details.get('dimension_unit', 'inches'),
                }]

            for item in line_items:
                payload = {
                    'sale_order_id': order.id,
                    'pieces': item.get('num_pieces') or item.get('pieces') or 1,
                    'weight': item.get('weight', 0),
                    'weight_unit': (item.get('weight_unit') or details.get('weight_unit') or 'lbs').lower()[:3],
                    'length': item.get('length', 48),
                    'width': item.get('width', 40),
                    'height': item.get('height', 48),
                    'dim_unit': normalize_dim_unit(item.get('dimension_unit') or details.get('dimension_unit') or item.get('dim_unit')),
                    'packaging_type': normalize_pkg(item.get('packaging_type')),
                    'freight_class': str(item.get('freight_class', '70')),
                    'cargo_desc': item.get('cargo_description') or item.get('description') or '',
                    'nmfc': item.get('nmfc_code') or item.get('nmfc') or '',
                }
                _logger.info("BiziShip: Creating Cargo Line: %s", json.dumps(payload, indent=2))
                order.biziship_cargo_line_ids.create(payload)
            
            # ── Smarty Residential Detection (run automatically after load) ──
            try:
                smarty_url = f"{api_utils.get_biziship_api_url(self.env)}/erp/validate-address"
                erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
                smarty_headers = {"X-ERP-API-Key": erp_api_key}

                # Origin check
                origin_state_obj = order.biziship_origin_state_id
                origin_payload = {
                    "street": order.biziship_origin_address or "",
                    "city":   order.biziship_origin_city or "",
                    "state":  origin_state_obj.code if origin_state_obj else "",
                    "zip":    order.biziship_origin_zip or "",
                }
                r_origin = requests.post(smarty_url, headers=smarty_headers, json=origin_payload, timeout=5)
                if r_origin.status_code == 200:
                    origin_rdi = r_origin.json().get("rdi")
                    order.biziship_origin_residential_warning = (
                        origin_rdi == "Residential" and not order.biziship_origin_residential
                    )
                    _logger.info("BiziShip Smarty Origin RDI: %s", origin_rdi)

                # Destination check
                dest_state_obj = order.biziship_dest_state_id
                dest_payload = {
                    "street": order.biziship_dest_address or "",
                    "city":   order.biziship_dest_city or "",
                    "state":  dest_state_obj.code if dest_state_obj else "",
                    "zip":    order.biziship_dest_zip or "",
                }
                r_dest = requests.post(smarty_url, headers=smarty_headers, json=dest_payload, timeout=5)
                if r_dest.status_code == 200:
                    dest_rdi = r_dest.json().get("rdi")
                    order.biziship_dest_residential_warning = (
                        dest_rdi == "Residential" and not order.biziship_dest_residential
                    )
                    _logger.info("BiziShip Smarty Dest RDI: %s", dest_rdi)

            except Exception as e:
                _logger.warning("BiziShip: Smarty residential check failed after load: %s", e)

            return True
        except Exception as e:
            _logger.exception("BiziShip: Error loading freight")
            raise UserError(_("Error loading freight: %s") % str(e))

class BizishipLoadFreightLine(models.TransientModel):
    _name = 'biziship.load.freight.line'
    _description = 'Load Saved Freight Line'

    wizard_id = fields.Many2one('biziship.load.freight.wizard', string='Wizard')
    freight_id = fields.Char(string='Freight ID')
    name = fields.Char(string='Name')
    
    # Summary fields for card display
    origin_info = fields.Char(string='Origin Summary')
    summary_info = fields.Char(string='Weight/Cargo Summary')
    creator_info = fields.Char(string='Creator Summary')

    def action_launch(self):
        self.ensure_one()
        return self.wizard_id.action_load_freight_from_id(self.freight_id)
