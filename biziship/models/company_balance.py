import logging

import requests

_logger = logging.getLogger(__name__)


class CompanyBalance:
    """Fetch the BiziShip account balance snapshot for the current user's company."""

    @staticmethod
    def get_company_balance(env):
        """
        Returns:
            dict: {'balance': float, 'asOfDate': 'YYYY-MM-DD'}, or None if there's
            nothing to show (not connected, no snapshot yet, or the call failed).
            Never raises - this is informational, not a blocking part of any flow.
        """
        try:
            user = env.user
            if not user.biziship_token:
                return None

            from odoo.addons.biziship.api_utils import get_biziship_api_url, get_erp_api_key

            api_url = get_biziship_api_url(env)
            url = f"{api_url.rstrip('/')}/erp/company/balance"
            erp_api_key = get_erp_api_key(env)
            user_email = (user.biziship_email if user.biziship_token and user.biziship_email else user.email) or ""

            headers = {
                "Authorization": f"Bearer {user.biziship_token}",
                "X-ERP-API-Key": erp_api_key,
                "X-User-Email": user_email,
            }

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                _logger.info("Company balance fetch non-200: status=%d", response.status_code)
                return None

            data = response.json()
            if data.get('balance') is None or not data.get('asOfDate'):
                return None
            return data

        except Exception as e:
            _logger.warning("Company balance fetch EXCEPTION: %s", str(e), exc_info=True)
            return None
