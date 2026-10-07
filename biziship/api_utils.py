import os
import json

# ==========================================
# ENVIRONMENT CONFIGURATION
# Set to 'PROD' to connect to AWS backend
# Set to 'DEV' to connect to local backend
# ==========================================
BIZISHIP_ENV = 'PROD'
BIZISHIP_MODULE_VERSION = '1.1.1.100226_4'
BIZISHIP_APP_NAME = 'biziShip.ai on Odoo'
# Default BiziShip ERP Gateway endpoint. Not a credential by itself — the gateway is
# unusable without a valid API key (see get_erp_api_key). Admins can override it in
# Settings > General Settings > BiziShip if they need to point at a different
# environment (e.g. staging).
BIZISHIP_DEFAULT_API_URL = 'https://6k90hxqjwe.execute-api.us-east-1.amazonaws.com/dev'

# Unit Conversion Constants
KG_TO_LBS = 2.20462
CM_TO_IN = 0.393701
M_TO_IN = 39.3701
FT_TO_IN = 12.0

def convert_to_lbs(weight, unit):
    """Converts weight to lbs."""
    if not weight:
        return 0.0
    if unit == 'kg':
        return weight * KG_TO_LBS
    return weight

def convert_to_inches(dim, unit):
    """Converts dimension to inches."""
    if not dim:
        return 0.0
    if unit == 'cm':
        return dim * CM_TO_IN
    elif unit == 'm':
        return dim * M_TO_IN
    elif unit == 'ft':
        return dim * FT_TO_IN
    return dim

def get_secrets():
    secrets_path = os.path.join(os.path.dirname(__file__), 'secrets.json')
    if os.path.exists(secrets_path):
        with open(secrets_path, 'r') as f:
            return json.load(f)
    return {}

def get_biziship_api_url(env=None):
    """
    Returns the BiziShip ERP Gateway URL, with the following priority:
    1. Odoo System Parameter (ir.config_parameter: biziship.api_url) — settable via
       Settings > General Settings > BiziShip, for admins who need a non-default endpoint.
    2. Local secrets.json fallback (development only).
    3. The published default endpoint (BIZISHIP_DEFAULT_API_URL).
    """
    if env:
        url = env['ir.config_parameter'].sudo().get_param('biziship.api_url')
        if url:
            return url.rstrip('/')

    if BIZISHIP_ENV != 'PROD':
        secrets = get_secrets()
        dev_url = secrets.get("EMAIL2QUOTE_API_URL")
        if dev_url:
            return dev_url.rstrip('/')

    return BIZISHIP_DEFAULT_API_URL

def get_email2quote_api_key():
    return get_secrets().get("EMAIL2QUOTE_API_KEY", "")

def fetch_biziship_user_profile(env):
    """
    Call GET /erp/auth/me and return the profile dict, or None on failure.
    Response keys: id, email, fullName, role, priority1Env, demoTries, companyId, companyName
    """
    import requests
    import logging
    _logger = logging.getLogger(__name__)
    try:
        user = env.user
        erp_api_key = get_erp_api_key(env)
        email = (
            user.biziship_email
            if user.biziship_token and user.biziship_email
            else user.email
        ) or ""
        url = f"{get_biziship_api_url(env)}/erp/auth/me"
        headers = {"X-ERP-API-Key": erp_api_key, "X-User-Email": email}
        if user.biziship_token:
            headers["Authorization"] = f"Bearer {user.biziship_token}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        _logger.error("BiziShip /auth/me error: %s", e)
    return None


def get_erp_api_key(env=None):
    """
    Returns the ERP API Key with the following priority:
    1. Odoo System Parameter (ir.config_parameter: biziship.erp_api_key) — settable via
       Settings > General Settings > BiziShip.
    2. Odoo Config File (odoo.conf: biziship_erp_api_key)
    3. OS Environment Variable (BIZISHIP_ERP_API_KEY)
    4. Local secrets.json fallback (development only)

    Raises a UserError if none of the above are configured — there is no built-in
    fallback key. Each installation must supply its own BiziShip API key.
    """
    key = None

    # 1. System Parameters (Best for UI management)
    if env:
        key = env['ir.config_parameter'].sudo().get_param('biziship.erp_api_key')

    # 2. Odoo Config File (odoo.conf)
    if not key:
        try:
            from odoo.tools import config
            key = config.get('biziship_erp_api_key')
        except ImportError:
            pass

    # 3. Environment Variables (Best for Docker/Cloud deployments)
    if not key:
        key = os.environ.get('BIZISHIP_ERP_API_KEY')

    # 4. Local secrets.json Fallback
    if not key:
        secrets = get_secrets()
        key = secrets.get("BIZISHIP_ERP_GATEWAY_KEY") or secrets.get("EMAIL2QUOTE_API_KEY")

    if not key:
        from odoo.exceptions import UserError
        from odoo.tools.translate import _
        raise UserError(_(
            "BiziShip API key not configured. Go to Settings > General Settings > "
            "BiziShip and enter your API key, or ask your administrator to do so."
        ))

    return key


def poll_bol_extraction(env, job_id, api_url):
    """
    Poll the BiziShip BOL extraction job until completion, error, or timeout.

    Args:
        env: Odoo environment
        job_id: The UUID returned from POST /erp/bol/extract (202 response)
        api_url: Base API URL for the BiziShip backend

    Returns:
        dict: The extracted_details on success

    Raises:
        UserError: On polling error, timeout, or extraction failure
    """
    import requests
    import time
    import logging
    from odoo.exceptions import UserError
    from odoo.tools.translate import _
    _logger = logging.getLogger(__name__)

    poll_url = f"{api_url.rstrip('/')}/erp/bol/jobs/{job_id}"
    poll_interval = 1.5  # seconds
    hard_timeout = 20  # slightly past expected 15s limit
    start_time = time.time()
    poll_count = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > hard_timeout:
            raise UserError(
                _("BOL parsing took too long (over 15 seconds). Please try again.")
            )

        try:
            # jobId is the bearer token — send it in Authorization header
            # Also include ERP API key for identification/rate-limiting
            erp_api_key = get_erp_api_key(env)
            poll_headers = {
                "Authorization": f"Bearer {job_id}",
                "X-ERP-API-Key": erp_api_key,
            }
            poll_response = requests.get(poll_url, headers=poll_headers, timeout=10)
            poll_count += 1
            _logger.info("BOL Poll #%d (elapsed %.1fs): status %d", poll_count, elapsed, poll_response.status_code)

            if poll_response.status_code == 404:
                raise UserError(
                    _("BOL extraction job not found. The job may have expired.")
                )

            if poll_response.status_code != 200:
                # Transient network error — log and retry
                _logger.warning(
                    "BOL polling got non-200 status %d, retrying in %.1fs",
                    poll_response.status_code, poll_interval
                )
                time.sleep(poll_interval)
                continue

            response_json = poll_response.json()
            status = response_json.get('status')

            if status == 'processing':
                time.sleep(poll_interval)
                continue

            elif status == 'done':
                extracted = response_json.get('extracted_details', {})
                _logger.info("BOL extraction succeeded after %.1fs (%d polls)", elapsed, poll_count)
                return extracted

            elif status == 'error':
                error_msg = response_json.get('error', 'Unknown error')
                raise UserError(
                    _("BOL parsing failed: %s\n\nPlease upload another BOL or enter details manually.") % error_msg
                )

            elif status == 'expired':
                error_msg = response_json.get('error', 'Job expired')
                raise UserError(
                    _("BOL extraction timed out. %s\n\nPlease try again.") % error_msg
                )

            else:
                raise UserError(
                    _("Unknown BOL extraction status: %s") % status
                )

        except requests.exceptions.Timeout:
            _logger.warning("BOL polling request timed out, retrying")
            time.sleep(poll_interval)
        except requests.exceptions.RequestException as e:
            _logger.warning("BOL polling request failed: %s, retrying", str(e))
            time.sleep(poll_interval)
