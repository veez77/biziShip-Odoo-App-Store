from odoo import models, fields

class BizishipAccessorial(models.Model):
    _name = 'biziship.accessorial'
    _description = 'BiziShip Accessorial Service'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)
    type = fields.Selection([
        ('origin', 'Pickup (Origin)'),
        ('destination', 'Delivery (Destination)')
    ], string='Type', required=True)
