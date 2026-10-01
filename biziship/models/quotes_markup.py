import requests
from odoo.exceptions import UserError
from odoo import _
import logging

_logger = logging.getLogger(__name__)


class QuotesMarkup:
    """Handle quote markup (margin pricing) configuration and application."""

    @staticmethod
    def get_company_markup_config(env):
        """
        Fetch markup configuration for the current user's company from backend.

        Returns:
            dict: {
                'enabled': bool,
                'ruleType': 'FLAT' | 'PERCENT' | 'TIERED' | None,
                'flatAmount': float | None,
                'percentValue': float | None,
                'tiers': [...] | None,  # only if ruleType == 'TIERED'
            }
            or None if fetch fails (non-fatal, just don't show markup UI)
        """
        try:
            user = env.user
            if not user.biziship_token:
                _logger.info("get_company_markup_config: No BiziShip token for user %s", user.email)
                return None

            from odoo.addons.biziship.api_utils import get_biziship_api_url, get_erp_api_key

            api_url = get_biziship_api_url(env)
            url = f"{api_url.rstrip('/')}/erp/company/markup-config"
            erp_api_key = get_erp_api_key(env)
            user_email = (user.biziship_email if user.biziship_token and user.biziship_email else user.email) or ""

            headers = {
                "Authorization": f"Bearer {user.biziship_token}",
                "X-ERP-API-Key": erp_api_key,
                "X-User-Email": user_email,
            }

            _logger.info("get_company_markup_config: Calling endpoint=%s user_email=%s erp_key_present=%s",
                        url, user_email, bool(erp_api_key))

            response = requests.get(url, headers=headers, timeout=10)

            _logger.info("get_company_markup_config: Response status=%d", response.status_code)

            if response.status_code == 200:
                config = response.json()
                _logger.info("Markup config fetched SUCCESS: enabled=%s, ruleType=%s, full_response=%s",
                            config.get('enabled'), config.get('ruleType'), config)
                return config

            _logger.warning("Markup config fetch FAILED: status=%d, response_body=%s", response.status_code, response.text)
            return None

        except Exception as e:
            _logger.warning("Markup config fetch EXCEPTION: %s", str(e), exc_info=True)
            return None

    @staticmethod
    def apply_markup(price, markup_config):
        """
        Apply markup to a price based on company configuration.

        Args:
            price: float, the original price to mark up
            markup_config: dict from get_company_markup_config()

        Returns:
            float: marked-up price, or original price if markup not applicable
        """
        if not markup_config or not markup_config.get('enabled'):
            return price

        if price is None:
            return price

        rule_type = markup_config.get('ruleType')

        if rule_type == 'FLAT':
            flat_amount = markup_config.get('flatAmount')
            if flat_amount is not None:
                return price + flat_amount
            return price

        elif rule_type == 'PERCENT':
            percent_value = markup_config.get('percentValue')
            if percent_value is not None:
                return price + price * (percent_value / 100.0)
            return price

        elif rule_type == 'TIERED':
            tiers = markup_config.get('tiers', [])
            if tiers:
                return QuotesMarkup._apply_tiered(price, tiers)
            return price

        return price

    @staticmethod
    def _apply_tiered(price, tiers):
        """
        Apply tiered (bracket) markup rule to a price.

        Tiers are cliff-based: find the first tier where price <= tier.upToPrice
        (or tier.upToPrice is null for open-ended), then apply that tier's rule.

        Args:
            price: float
            tiers: list of { 'upToPrice': float|null, 'ruleType': 'FLAT'|'PERCENT', 'value': float }

        Returns:
            float: marked-up price
        """
        # Sort tiers by upToPrice ascending (None goes last = open-ended)
        sorted_tiers = sorted(
            tiers,
            key=lambda t: t.get('upToPrice') if t.get('upToPrice') is not None else float('inf')
        )

        # Find matching tier (cliff-based, not graduated)
        for tier in sorted_tiers:
            up_to_price = tier.get('upToPrice')
            if up_to_price is None or price <= up_to_price:
                # Apply this tier's rule
                rule_type = tier.get('ruleType', 'FLAT')
                value = tier.get('value', 0)

                if rule_type == 'PERCENT':
                    return price + price * (value / 100.0)
                else:  # FLAT
                    return price + value

        # Fallback: no matching tier (shouldn't happen if tiers are well-formed)
        return price

    @staticmethod
    def format_markup_description(markup_config):
        """
        Generate human-readable description of markup rule.

        Returns:
            str: e.g. "+$50.00", "+10%", or tiered description
        """
        if not markup_config or not markup_config.get('enabled'):
            return ""

        rule_type = markup_config.get('ruleType')

        if rule_type == 'FLAT':
            amount = markup_config.get('flatAmount')
            if amount is not None:
                return f"+${amount:,.2f} added to each carrier price"
            return ""

        elif rule_type == 'PERCENT':
            percent = markup_config.get('percentValue')
            if percent is not None:
                return f"+{percent:.0f}% added to each carrier price"
            return ""

        elif rule_type == 'TIERED':
            tiers = markup_config.get('tiers', [])
            if not tiers:
                return ""
            # Build a description like "Up to $500: +$50, $500+: +10%"
            parts = []
            sorted_tiers = sorted(
                tiers,
                key=lambda t: t.get('upToPrice') if t.get('upToPrice') is not None else float('inf')
            )
            for tier in sorted_tiers:
                up_to = tier.get('upToPrice')
                rule_type_t = tier.get('ruleType', 'FLAT')
                value = tier.get('value', 0)

                if rule_type_t == 'PERCENT':
                    rule_str = f"+{value:.0f}%"
                else:
                    rule_str = f"+${value:,.2f}"

                if up_to is None:
                    parts.append(f"Above ${up_to:,.2f}: {rule_str}")
                elif up_to is not None and len(parts) == 0:
                    parts.append(f"Up to ${up_to:,.2f}: {rule_str}")
                else:
                    prev_up_to = sorted_tiers[sorted_tiers.index(tier) - 1].get('upToPrice', 0)
                    parts.append(f"${prev_up_to:,.2f}–${up_to:,.2f}: {rule_str}")

            return " | ".join(parts)

        return ""
