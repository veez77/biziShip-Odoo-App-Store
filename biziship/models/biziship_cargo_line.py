from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
from odoo.addons.biziship.api_utils import KG_TO_LBS, CM_TO_IN, M_TO_IN, FT_TO_IN, convert_to_lbs

class BizishipSaleCargoLine(models.Model):
    _name = 'biziship.sale.cargo.line'
    _description = 'BiziShip Sale Cargo Line'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade')
    sequence = fields.Integer(string="Sequence", default=10)
    display_name = fields.Char(compute='_compute_display_name')

    @api.depends('sale_order_id.biziship_cargo_line_ids', 'sequence')
    def _compute_display_name(self):
        for rec in self:
            if not rec.sale_order_id:
                rec.display_name = "New Item"
                continue
            # Find the position of this record among all lines of the same order
            lines = rec.sale_order_id.biziship_cargo_line_ids.sorted('sequence')
            try:
                # Using list index to find the 1-based position
                pos = list(lines._ids).index(rec.id) + 1 if rec.id in lines._ids else len(lines)
                # If it's a new record in cache, it might not have an ID yet in some cases
                if rec.id in lines._ids:
                    rec.display_name = f"Item #{pos}"
                else:
                    # Fallback for new unsaved records
                    rec.display_name = f"Item #{len(lines)}" 
            except ValueError:
                rec.display_name = "Item"

    packaging_type = fields.Selection([
        ('pallet', 'Pallet'),
        ('crate', 'Crate'),
        ('box', 'Box'),
        ('drum', 'Drum'),
    ], string="Packaging Type", default="pallet", required=True)
    
    pieces = fields.Integer(string="Pieces (Handling Units)", default=1, required=True)
    
    weight = fields.Float(string="Weight", default=0.0, required=True)
    weight_unit = fields.Selection([('lbs', 'lbs'), ('kg', 'kg')], string="Weight Unit", default='lbs', required=True)
    
    # Technical trackers for immediate conversion (not stored in DB)
    last_weight_unit = fields.Selection([('lbs', 'lbs'), ('kg', 'kg')], store=False)
    last_dim_unit = fields.Selection([('in', 'in'), ('cm', 'cm'), ('m', 'm'), ('ft', 'ft')], store=False)

    @api.onchange('weight_unit')
    def _onchange_weight_unit(self):
        for rec in self:
            # First-time initialization from saved state if tracker is empty
            if not rec.last_weight_unit:
                rec.last_weight_unit = rec._origin.weight_unit or 'lbs'
                
            if rec.last_weight_unit != rec.weight_unit and rec.weight:
                if rec.weight_unit == 'kg' and rec.last_weight_unit == 'lbs':
                    rec.weight = round(rec.weight / KG_TO_LBS, 2)
                elif rec.weight_unit == 'lbs' and rec.last_weight_unit == 'kg':
                    rec.weight = round(rec.weight * KG_TO_LBS, 2)
            
            # Update tracker for the NEXT change in the same session
            rec.last_weight_unit = rec.weight_unit
    
    length = fields.Float(string="Length", default=48.0, required=True)
    width = fields.Float(string="Width", default=40.0, required=True)
    height = fields.Float(string="Height", default=48.0, required=True)
    dim_unit = fields.Selection([('in', 'in'), ('cm', 'cm'), ('m', 'm'), ('ft', 'ft')], string="Dim Unit", default='in', required=True)

    @api.onchange('dim_unit')
    def _onchange_dim_unit(self):
        for rec in self:
            # First-time initialization from saved state if tracker is empty
            if not rec.last_dim_unit:
                rec.last_dim_unit = rec._origin.dim_unit or 'in'
                
            if rec.last_dim_unit != rec.dim_unit:
                def convert_dim(val, from_u, to_u):
                    if not val: return val
                    in_val = val
                    if from_u == 'cm': in_val = val * CM_TO_IN
                    elif from_u == 'm': in_val = val * M_TO_IN
                    elif from_u == 'ft': in_val = val * FT_TO_IN
                    out_val = in_val
                    if to_u == 'cm': out_val = in_val / CM_TO_IN
                    elif to_u == 'm': out_val = in_val / M_TO_IN
                    elif to_u == 'ft': out_val = in_val / FT_TO_IN
                    return round(out_val, 2)
                    
                rec.length = convert_dim(rec.length, rec.last_dim_unit, rec.dim_unit)
                rec.width = convert_dim(rec.width, rec.last_dim_unit, rec.dim_unit)
                rec.height = convert_dim(rec.height, rec.last_dim_unit, rec.dim_unit)
            
            # Update tracker for the NEXT change in the same session
            rec.last_dim_unit = rec.dim_unit
    
    freight_class = fields.Selection([
        ('50', '50'), ('55', '55'), ('60', '60'), ('65', '65'),
        ('70', '70'), ('85', '85'), ('92.5', '92.5'),
        ('100', '100'), ('125', '125'), ('175', '175'),
        ('250', '250'), ('300', '300'), ('400', '400')
    ], string="Class", default='50', required=True)

    computed_freight_class = fields.Selection([
        ('50', '50'), ('55', '55'), ('60', '60'), ('65', '65'),
        ('70', '70'), ('85', '85'), ('92.5', '92.5'),
        ('100', '100'), ('125', '125'), ('175', '175'),
        ('250', '250'), ('300', '300'), ('400', '400')
    ], string="Computed Class", compute='_compute_computed_class', store=True)
    
    is_class_overridden = fields.Boolean(compute='_compute_is_class_overridden')
    nmfc = fields.Char(string="NMFC")
    hazmat = fields.Boolean(string="Hazardous Material", default=False)
    stackable = fields.Boolean(string="Stackable", default=False)
    used = fields.Boolean(string="Used / Reconditioned", default=False)
    machinery = fields.Boolean(string="Machinery", default=False)
    nmfc_suggestion_data = fields.Text(string="NMFC Suggestion Data")
    cargo_desc = fields.Char(string="Cargo Description")
    
    # NMFC Suggestion Fields
    nmfc_suggested_code = fields.Char(string="Suggested NMFC")
    nmfc_suggestion_confidence = fields.Float(string="Suggestion Confidence")
    nmfc_suggestion_label = fields.Selection([
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low')
    ], string="Suggestion Label")
    nmfc_suggestion_rationale = fields.Text(string="Suggestion Rationale")
    nmfc_applied_desc = fields.Char(string="Applied Description") # To detect staleness
    nmfc_alternative_json = fields.Text(string="Alternative Suggestions JSON")
    nmfc_is_stale = fields.Boolean(compute='_compute_nmfc_is_stale')
    is_processing = fields.Boolean(string="Processing", default=False, store=False)

    @api.depends('nmfc', 'cargo_desc', 'nmfc_applied_desc')
    def _compute_nmfc_is_stale(self):
        for rec in self:
            rec.nmfc_is_stale = bool(rec.nmfc and rec.nmfc_applied_desc and rec.cargo_desc != rec.nmfc_applied_desc)

    def action_biziship_nmfc_suggest(self):
        """Proxies call to ERP Gateway /erp/nmfc/suggest."""
        self.ensure_one()
        from odoo.addons.biziship import api_utils
        import requests
        import logging
        _logger = logging.getLogger(__name__)

        api_url = f"{api_utils.get_biziship_api_url(self.env).rstrip('/')}/erp/nmfc/suggest"
        erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
        
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "Content-Type": "application/json",
        }

        # Convert dimensions to inches for the API
        dims = {
            "length": round(api_utils.convert_to_inches(self.length, self.dim_unit), 2),
            "width": round(api_utils.convert_to_inches(self.width, self.dim_unit), 2),
            "height": round(api_utils.convert_to_inches(self.height, self.dim_unit), 2),
        }

        # Collect flags
        flags = []
        if self.hazmat: flags.append("hazmat")
        if self.stackable: flags.append("stackable")
        if self.used: flags.append("used_reconditioned")
        if self.machinery: flags.append("machinery")

        payload = {
            "commodityDescription": self.cargo_desc or "",
            "handlingUnit": self.packaging_type or "pallet",
            "pieces": self.pieces or 1,
            "weight": round(api_utils.convert_to_lbs(self.weight, self.weight_unit), 2),
            "dimensions": dims,
            "calculatedClass": self.computed_freight_class or self.freight_class or "50",
            "flags": flags
        }

        try:
            _logger.info("NMFC Suggest Request: %s", json.dumps(payload))
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                _logger.info("NMFC Suggest Response: %s", json.dumps(data))
                
                self.write({
                    'nmfc_suggested_code': data.get('suggestedNmfc'),
                    'nmfc_suggestion_confidence': data.get('confidence'),
                    'nmfc_suggestion_label': data.get('confidenceLabel'),
                    'nmfc_suggestion_rationale': data.get('rationale'),
                    'nmfc_alternative_json': json.dumps(data.get('alternativeSuggestions', []))
                })
                
                # If HIGH confidence, auto-apply unless user manually edited it? 
                # Prompt says: "HIGH: Auto-fill NMFC silently (no user action needed)"
                # "Do NOT re-suggest if the user has manually typed into the NMFC field."
                # We'll handle the "manually typed" check in JS mostly, but for this proxy call:
                if data.get('confidenceLabel') == 'high' and data.get('suggestedNmfc'):
                    self.write({
                        'nmfc': data.get('suggestedNmfc'),
                        'nmfc_applied_desc': self.cargo_desc
                    })
                
                return data
            else:
                _logger.warning("NMFC Suggest Error: %s - %s", response.status_code, response.text)
        except Exception as e:
            _logger.error("NMFC Suggest Exception: %s", str(e))
            
        return False

    @api.constrains('pieces')
    def _check_pieces(self):
        for rec in self:
            if rec.pieces <= 0:
                raise models.ValidationError("Pieces must be greater than 0.")

    @api.onchange('weight', 'weight_unit', 'length', 'width', 'height', 'dim_unit', 'pieces')
    def _onchange_cargo_recompute_class(self):
        """Standard density-based class re-calculation logic."""
        self._compute_computed_class()
        if self.computed_freight_class:
            self.freight_class = self.computed_freight_class

    @api.depends('weight', 'weight_unit', 'length', 'width', 'height', 'dim_unit', 'pieces')
    def _compute_computed_class(self):
        for rec in self:
            if rec.length and rec.width and rec.height and rec.weight and rec.pieces:
                l, w, h = rec.length, rec.width, rec.height
                if rec.dim_unit == 'cm':
                    l, w, h = l * CM_TO_IN, w * CM_TO_IN, h * CM_TO_IN
                elif rec.dim_unit == 'm':
                    l, w, h = l * M_TO_IN, w * M_TO_IN, h * M_TO_IN
                elif rec.dim_unit == 'ft':
                    l, w, h = l * FT_TO_IN, w * FT_TO_IN, h * FT_TO_IN
                    
                volume_cf = (l * w * h) / 1728.0
                if volume_cf > 0:
                    effective_weight = convert_to_lbs(rec.weight, rec.weight_unit)
                    density = effective_weight / volume_cf
                    # Priority1 corrected density thresholds (13-class system)
                    if density >= 50.0:
                        rec.computed_freight_class = '50'
                    elif density >= 35.0:
                        rec.computed_freight_class = '55'
                    elif density >= 30.0:
                        rec.computed_freight_class = '60'
                    elif density >= 22.5:
                        rec.computed_freight_class = '65'
                    elif density >= 15.0:
                        rec.computed_freight_class = '70'
                    elif density >= 12.0:
                        rec.computed_freight_class = '85'
                    elif density >= 10.0:
                        rec.computed_freight_class = '92.5'
                    elif density >= 8.0:
                        rec.computed_freight_class = '100'
                    elif density >= 6.0:
                        rec.computed_freight_class = '125'
                    elif density >= 4.0:
                        rec.computed_freight_class = '175'
                    elif density >= 2.0:
                        rec.computed_freight_class = '250'
                    elif density >= 1.0:
                        rec.computed_freight_class = '300'
                    else:
                        rec.computed_freight_class = '400'
                else:
                    rec.computed_freight_class = '50'
            else:
                rec.computed_freight_class = False

    line_total_weight_display = fields.Char(compute='_compute_line_total_weight_display', store=False)

    @api.depends('weight', 'weight_unit', 'pieces')
    def _compute_line_total_weight_display(self):
        for rec in self:
            if rec.weight and rec.pieces:
                total = convert_to_lbs(rec.weight, rec.weight_unit) * rec.pieces
                rec.line_total_weight_display = f"= {total:,.0f} lbs"
            else:
                rec.line_total_weight_display = ""

    @api.depends('freight_class', 'computed_freight_class')
    def _compute_is_class_overridden(self):
        for rec in self:
            rec.is_class_overridden = (
                rec.freight_class and rec.computed_freight_class
                and rec.freight_class != rec.computed_freight_class
            )

    # Non-stored trigger field — used only to attach the NMFC Favorites widget in the kanban card
    biziship_nmfc_fav_trigger = fields.Boolean(compute='_compute_nmfc_fav_trigger', store=False)

    def _compute_nmfc_fav_trigger(self):
        for rec in self:
            rec.biziship_nmfc_fav_trigger = False

    @api.model
    def action_biziship_get_nmfc_favorites(self):
        """Fetch company NMFC favorites from BiziShip API."""
        import requests
        import logging
        _logger = logging.getLogger(__name__)
        from odoo.addons.biziship import api_utils

        base_url = api_utils.get_biziship_api_url(self.env).rstrip('/')
        erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
        user = self.env.user
        user_email = (user.biziship_email if user.biziship_token and user.biziship_email else user.email) or ""
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "X-User-Email": user_email,
        }
        try:
            response = requests.get(f"{base_url}/erp/company/nmfc-favorites", headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json().get('favorites', [])
            _logger.warning("NMFC Favorites GET error: %s - %s", response.status_code, response.text)
            return []
        except Exception as e:
            _logger.error("NMFC Favorites GET exception: %s", str(e))
            return []

    @api.model
    def action_biziship_save_nmfc_favorite(self, description=None, nmfc_code=None):
        """Save a new NMFC favorite to BiziShip API."""
        import requests
        import logging
        _logger = logging.getLogger(__name__)
        from odoo.addons.biziship import api_utils

        if not description or not nmfc_code:
            raise UserError(_("Both description and NMFC code are required."))

        base_url = api_utils.get_biziship_api_url(self.env).rstrip('/')
        erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
        user = self.env.user
        user_email = (user.biziship_email if user.biziship_token and user.biziship_email else user.email) or ""
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "X-User-Email": user_email,
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                f"{base_url}/erp/company/nmfc-favorites",
                headers=headers,
                json={"description": description, "nmfc_code": nmfc_code},
                timeout=10,
            )
            if response.status_code == 201:
                return response.json()
            error_msg = response.text
            try:
                error_msg = response.json().get('detail', error_msg)
            except Exception:
                pass
            raise UserError(error_msg or _("Failed to save NMFC favorite."))
        except UserError:
            raise
        except Exception as e:
            _logger.error("NMFC Favorites POST exception: %s", str(e))
            raise UserError(_("Error connecting to BiziShip: %s") % str(e))

    @api.model
    def action_biziship_delete_nmfc_favorite(self, favorite_id=None):
        """Delete an NMFC favorite from BiziShip API."""
        import requests
        import logging
        _logger = logging.getLogger(__name__)
        from odoo.addons.biziship import api_utils

        base_url = api_utils.get_biziship_api_url(self.env).rstrip('/')
        erp_api_key = self.env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key', '')
        user = self.env.user
        user_email = (user.biziship_email if user.biziship_token and user.biziship_email else user.email) or ""
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "X-User-Email": user_email,
        }
        try:
            response = requests.delete(
                f"{base_url}/erp/company/nmfc-favorites/{favorite_id}",
                headers=headers,
                timeout=10,
            )
            return response.status_code == 204
        except Exception as e:
            _logger.error("NMFC Favorites DELETE exception: %s", str(e))
            return False
