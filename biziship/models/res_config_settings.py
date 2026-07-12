from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Stored as System Parameters (ir.config_parameter) via the config_parameter
    # attribute — this is the only place the BiziShip credentials live; nothing is
    # hardcoded in the module itself. See api_utils.get_erp_api_key / get_biziship_api_url.
    biziship_erp_api_key = fields.Char(
        string="BiziShip API Key",
        config_parameter='biziship.erp_api_key',
        help="Your BiziShip.ai ERP Gateway API key. Get yours from your BiziShip.ai account "
             "dashboard or by contacting BiziShip.ai support.",
    )
    biziship_api_url = fields.Char(
        string="BiziShip API URL",
        config_parameter='biziship.api_url',
        help="Only needed if BiziShip.ai instructs you to point at a different endpoint "
             "(e.g. a staging environment). Leave blank to use the default.",
    )
