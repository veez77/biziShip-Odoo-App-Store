import requests
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

from .. import api_utils
from ..api_utils import get_erp_api_key

class BizishipAuthWizard(models.TransientModel):
    _name = 'biziship.auth.wizard'
    _description = 'BiziShip Authentication Wizard'

    email = fields.Char(string='Email', required=True)
    pin = fields.Char(string='PIN Code')
    state = fields.Selection([
        ('request', 'Request PIN'),
        ('verify', 'Verify PIN')
    ], default='request')
    sale_order_id = fields.Many2one('sale.order')

    @api.model
    def default_get(self, fields):
        res = super(BizishipAuthWizard, self).default_get(fields)
        if 'email' in fields and not res.get('email'):
            res['email'] = self.env.user.email
        if 'sale_order_id' in fields and not res.get('sale_order_id'):
            ctx = self.env.context
            if ctx.get('active_model') == 'sale.order' and ctx.get('active_id'):
                res['sale_order_id'] = ctx['active_id']
        return res

    def action_request_pin(self):
        erp_api_key = get_erp_api_key(self.env)
        base_url = api_utils.get_biziship_api_url(self.env)
        url = f"{base_url}/erp/auth/login"
        payload = {'email': self.email}
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "Content-Type": "application/json",
            "X-Client-App": api_utils.BIZISHIP_APP_NAME,
            "X-Client-Version": api_utils.BIZISHIP_MODULE_VERSION,
        }
        
        _logger.info("BiziShip Login Request URL: %s", url)
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                self.state = 'verify'
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'biziship.auth.wizard',
                    'view_mode': 'form',
                    'res_id': self.id,
                    'target': 'new',
                }
            else:
                error_msg = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get('message', error_msg)
                except:
                    pass
                raise UserError(_("Failed to request PIN (Status %s): %s") % (response.status_code, error_msg))
        except UserError:
            raise
        except Exception as e:
            _logger.error("BiziShip PIN Request Error: %s", str(e), exc_info=True)
            raise UserError(_("Error connecting to BiziShip (%s): %s") % (type(e).__name__, str(e)))

    def action_verify_pin(self):
        erp_api_key = get_erp_api_key(self.env)
        base_url = api_utils.get_biziship_api_url(self.env)
        url = f"{base_url}/erp/auth/verify-pin"
        payload = {
            'email': self.email,
            'pin': self.pin
        }
        headers = {
            "X-ERP-API-Key": erp_api_key,
            "Content-Type": "application/json",
            "X-Client-App": api_utils.BIZISHIP_APP_NAME,
            "X-Client-Version": api_utils.BIZISHIP_MODULE_VERSION,
        }
        
        _logger.info("BiziShip PIN Verify URL: %s", url)
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                token = data.get('token')
                user_data = data.get('user', {})
                env = user_data.get('priority1Env', 'DEV')
                user_name = user_data.get('name') or user_data.get('email', 'Connected User')
                
                # Save BiziShip email (the email Andy used to register with BiziShip)
                # and the display name separately. The biziship_email field is what
                # gets sent as X-User-Email in all API calls to the BiziShip backend.
                self.env.user.write({
                    'biziship_token': token,
                    'biziship_email': self.email,
                    'biziship_user_name': user_name,
                    'biziship_p1_env': env
                })

                # Navigate back to the sale order that opened this wizard.
                # self.sale_order_id is set in default_get when the wizard opens from a
                # sale.order form button; it survives the action_request_pin dialog reload
                # unlike context['active_id'], which gets overwritten with the wizard's own
                # ID by doActionButton when Verify PIN is clicked — causing the client to
                # call webRead('sale.order', [<wizard_id>]) → FetchRecordError.
                next_action = {'type': 'ir.actions.act_window_close'}
                if self.sale_order_id and self.sale_order_id.exists():
                    next_action = {
                        'type': 'ir.actions.act_window',
                        'res_model': 'sale.order',
                        'res_id': self.sale_order_id.id,
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                        'target': 'current',
                    }

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Successfully connected to BiziShip as %s!') % user_name,
                        'type': 'success',
                        'sticky': False,
                        'next': next_action,
                    }
                }
            else:
                error_msg = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get('message', error_msg)
                except:
                    pass
                raise UserError(_("Invalid PIN (Status %s): %s") % (response.status_code, error_msg))
        except UserError:
            raise
        except Exception as e:
            _logger.error("BiziShip PIN Verify Error: %s", str(e), exc_info=True)
            raise UserError(_("Error connecting to BiziShip (%s): %s") % (type(e).__name__, str(e)))
