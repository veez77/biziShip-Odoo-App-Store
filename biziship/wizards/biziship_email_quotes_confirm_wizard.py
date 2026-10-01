import re
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class BizishipEmailQuotesConfirmWizard(models.TransientModel):
    _name = 'biziship.email.quotes.confirm.wizard'
    _description = 'Confirm Email Recipients Before Sending'

    sale_order_id = fields.Many2one('sale.order', readonly=True)
    to_emails = fields.Text(readonly=True)
    apply_markup = fields.Boolean(readonly=True)
    emails_display_html = fields.Html(compute='_compute_emails_display')
    has_invalid_emails = fields.Boolean(compute='_compute_emails_display', store=True)

    @api.depends('to_emails')
    def _compute_emails_display(self):
        """Validate and display emails with highlights. Set has_invalid_emails based on results."""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9]+\.)+[a-zA-Z]{2,}$'

        for record in self:
            if not record.to_emails:
                record.emails_display_html = ''
                record.has_invalid_emails = False
                continue

            emails = [e.strip() for e in record.to_emails.replace(';', ',').replace(' ', ',').split(',')]
            emails = [e for e in emails if e]

            html_lines = []
            has_invalid = False
            for email in emails:
                is_valid = bool(re.match(email_pattern, email))
                if is_valid:
                    html_lines.append(f'<div style="padding: 8px; margin: 4px 0; background: #f0fdf4; border-left: 3px solid #16a34a; color: #15803d;"><strong>✓</strong> {email}</div>')
                else:
                    html_lines.append(f'<div style="padding: 8px; margin: 4px 0; background: #fef2f2; border-left: 3px solid #dc2626; color: #991b1b;"><strong>⚠</strong> {email} <span style="font-size: 12px;">(invalid format)</span></div>')
                    has_invalid = True

            html = '<div style="border: 1px solid #e5e7eb; border-radius: 4px; padding: 12px;">' + ''.join(html_lines) + '</div>'
            record.emails_display_html = html
            record.has_invalid_emails = has_invalid

    def action_cancel(self):
        """Close dialog and return to email wizard."""
        return {
            'type': 'ir.actions.act_window_close',
        }

    def action_confirm_and_send(self):
        """Send the report to the confirmed recipients."""
        if not self.to_emails or not self.to_emails.strip():
            return

        emails = [e.strip() for e in self.to_emails.replace(';', ',').replace(' ', ',').split(',')]
        emails = [e for e in emails if e]

        so = self.sale_order_id
        if not so:
            return

        # Call the actual send on the email wizard (which has the HTML report)
        # We'll pass the emails list and proceed with sending
        import requests
        from odoo.addons.biziship import api_utils

        request_id = so.biziship_quote_request_id
        if not request_id:
            return

        user = self.env.user
        if not user.biziship_token:
            return

        api_url = api_utils.get_biziship_api_url(self.env)
        erp_key = api_utils.get_erp_api_key(self.env)

        # Get the HTML report from the email wizard that was just used
        # We need to regenerate it here or pass it from the caller
        from odoo.addons.biziship.models.quotes_report_generator import QuotesReportGenerator
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

        # Build shipment data (same as email wizard)
        shipment_data = {
            'request_id': str(so.id),
            'po_number': so.biziship_po_number or '',
            'origin_company': so.biziship_origin_company or '',
            'origin_address': so.biziship_origin_address or '',
            'origin_address2': so.biziship_origin_address2 or '',
            'origin_city': so.biziship_origin_city or '',
            'origin_state': str(so.biziship_origin_state_id.code if so.biziship_origin_state_id else ''),
            'origin_zip': so.biziship_origin_zip or '',
            'origin_phone': so.biziship_origin_contact_phone or '',
            'destination_company': so.biziship_dest_company or '',
            'destination_address': so.biziship_dest_address or '',
            'destination_address2': so.biziship_dest_address2 or '',
            'destination_city': so.biziship_dest_city or '',
            'destination_state': str(so.biziship_dest_state_id.code if so.biziship_dest_state_id else ''),
            'destination_zip': so.biziship_dest_zip or '',
            'destination_phone': so.biziship_dest_contact_phone or '',
            'freight_lines': [
                {
                    'packaging_type': str(line.packaging_type or ''),
                    'pieces': int(line.pieces or 0),
                    'weight': float(line.weight or 0),
                    'weight_unit': str(line.weight_unit or 'lbs'),
                    'length': float(line.length or 0),
                    'width': float(line.width or 0),
                    'height': float(line.height or 0),
                    'dim_unit': str(line.dim_unit or 'in'),
                    'freight_class': str(line.freight_class or ''),
                    'nmfc': str(line.nmfc or ''),
                    'cargo_desc': str(line.cargo_desc or ''),
                    'hazmat': bool(line.hazmat),
                }
                for line in so.biziship_cargo_line_ids
            ],
        }

        quotes = [
            {
                'quote_id': str(q.id),
                'carrier_name': str(q.carrier_name or ''),
                'carrier_code': str(q.carrier_code or ''),
                'service_level': str(q.service_level or ''),
                'service_level_description': '',
                'transit_days': int(q.transit_days or 0),
                'delivery_date': str(q.delivery_date or ''),
                'total_charge': float(q.total_charge or 0),
                'currency': str(q.currency or 'USD'),
                'carrier_quote_number': str(q.quote_id_ref or ''),
                'carrier_liability_new': float(q.carrier_liability_new or 0),
                'carrier_liability_used': float(q.carrier_liability_used or 0),
            }
            for q in so.biziship_quote_ids
        ]

        # Generate HTML report with markup if enabled
        markup_config = None
        if self.apply_markup:
            markup_config = QuotesMarkup.get_company_markup_config(self.env)

        html_report = QuotesReportGenerator.generate_quotes_html_report(
            shipment_data=shipment_data,
            quotes=quotes,
            markup_config=markup_config,
            apply_markup=self.apply_markup
        )

        # Send via API
        url = f"{api_url.rstrip('/')}/erp/quote/{request_id}/email-report"
        headers = {
            'X-ERP-API-Key': erp_key,
            'Authorization': f'Bearer {user.biziship_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'to_emails': emails,
            'html_report': str(html_report),
        }

        try:
            _logger.info("Sending quote report to %s", emails)
            response = requests.post(url, json=payload, headers=headers, timeout=15)

            if response.status_code == 200:
                _logger.info("Quote report sent successfully to %s", emails)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
        except Exception as e:
            _logger.error("Failed to send report: %s", str(e), exc_info=True)
