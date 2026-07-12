from odoo import models, fields, api
from odoo.addons.biziship.api_utils import KG_TO_LBS, CM_TO_IN, M_TO_IN, FT_TO_IN, convert_to_lbs

class BizishipQuoteCargoLine(models.TransientModel):
    _name = 'biziship.quote.cargo.line'
    _description = 'BiziShip Quote Cargo Line'

    wizard_id = fields.Many2one('biziship.freight.quote.wizard', string='Wizard', required=True, ondelete='cascade')
    
    packaging_type = fields.Selection([
        ('pallet', 'Pallet'),
        ('crate', 'Crate'),
        ('box', 'Box'),
        ('drum', 'Drum'),
    ], string="Packaging Type", default="pallet", required=True)
    
    pieces = fields.Integer(string="Pieces (Handling Units)", default=1, required=True)
    
    weight = fields.Float(string="Weight", default=0.0, required=True)
    weight_unit = fields.Selection([('lbs', 'lbs'), ('kg', 'kg')], string="Weight Unit", default='lbs', required=True)
    
    # Technical trackers for immediate conversion
    last_weight_unit = fields.Selection([('lbs', 'lbs'), ('kg', 'kg')], store=False)
    last_dim_unit = fields.Selection([('in', 'in'), ('cm', 'cm'), ('m', 'm'), ('ft', 'ft')], store=False)

    @api.onchange('weight_unit')
    def _onchange_weight_unit(self):
        for rec in self:
            if not rec.last_weight_unit:
                rec.last_weight_unit = rec._origin.weight_unit or 'lbs'
                
            if rec.last_weight_unit != rec.weight_unit and rec.weight:
                if rec.weight_unit == 'kg' and rec.last_weight_unit == 'lbs':
                    rec.weight = round(rec.weight / KG_TO_LBS, 2)
                elif rec.weight_unit == 'lbs' and rec.last_weight_unit == 'kg':
                    rec.weight = round(rec.weight * KG_TO_LBS, 2)
            rec.last_weight_unit = rec.weight_unit
    
    length = fields.Float(string="Length", default=48.0, required=True)
    width = fields.Float(string="Width", default=40.0, required=True)
    height = fields.Float(string="Height", default=48.0, required=True)
    dim_unit = fields.Selection([('in', 'in'), ('cm', 'cm'), ('m', 'm'), ('ft', 'ft')], string="Dim Unit", default='in', required=True)
    @api.onchange('dim_unit')
    def _onchange_dim_unit(self):
        for rec in self:
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
            rec.last_dim_unit = rec.dim_unit
    
    freight_class = fields.Selection([
        ('50', '50'), ('55', '55'), ('60', '60'), ('65', '65'),
        ('70', '70'), ('77.5', '77.5'), ('85', '85'), ('92.5', '92.5'),
        ('100', '100'), ('110', '110'), ('125', '125'), ('150', '150'),
        ('175', '175'), ('250', '250'), ('300', '300'),
        ('400', '400'), ('500', '500')
    ], string="Class", default='50', required=True)
    
    cargo_desc = fields.Char(string="Cargo Description", default="General Freight")

    @api.onchange('weight', 'weight_unit', 'length', 'width', 'height', 'dim_unit', 'pieces')
    def _onchange_dimensions_for_class(self):
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
                    if density < 1: rec.freight_class = '500'
                    elif density < 2: rec.freight_class = '400'
                    elif density < 3: rec.freight_class = '300'
                    elif density < 4: rec.freight_class = '250'
                    elif density < 6: rec.freight_class = '175'
                    elif density < 7: rec.freight_class = '150'
                    elif density < 8: rec.freight_class = '125'
                    elif density < 9: rec.freight_class = '110'
                    elif density < 10.5: rec.freight_class = '100'
                    elif density < 12: rec.freight_class = '92.5'
                    elif density < 13.5: rec.freight_class = '85'
                    elif density < 15: rec.freight_class = '77.5'
                    elif density < 22.5: rec.freight_class = '70'
                    elif density < 30: rec.freight_class = '65'
                    elif density < 35: rec.freight_class = '60'
                    elif density < 50: rec.freight_class = '55'
                    else: rec.freight_class = '50'
                else:
                    rec.freight_class = '50'
