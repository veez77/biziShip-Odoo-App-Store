import logging
from odoo import api, models, fields
from .. import api_utils

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    biziship_token = fields.Char(string='BiziShip JWT Token', copy=False, groups='base.group_user')
    biziship_email = fields.Char(string='BiziShip Email', copy=False)
    biziship_user_name = fields.Char(string='BiziShip User Name', copy=False)
    biziship_p1_env = fields.Selection([('DEV', 'Development'), ('PROD', 'Production'), ('DEMO', 'Demo')], string='BiziShip Environment', copy=False)
    biziship_version = fields.Char(string='BiziShip.ai Version', compute='_compute_biziship_version')

    def _compute_biziship_version(self):
        for user in self:
            user.biziship_version = api_utils.BIZISHIP_MODULE_VERSION

    @api.model
    def _register_hook(self):
        """
        Self-healing hook that runs on every server startup.
        Creates the biziship_email column in PostgreSQL if it does not exist,
        preventing the UndefinedColumn crash caused by a failed module upgrade.
        """
        res = super()._register_hook()
        try:
            self.env.cr.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'res_users' AND column_name = 'biziship_email'"
            )
            if not self.env.cr.fetchone():
                _logger.warning("BiziShip: biziship_email column missing — creating it now")
                self.env.cr.execute(
                    "ALTER TABLE res_users ADD COLUMN biziship_email VARCHAR"
                )
                _logger.info("BiziShip: biziship_email column created successfully")
        except Exception as e:
            _logger.error("BiziShip: Could not create biziship_email column: %s", e)
        return res
