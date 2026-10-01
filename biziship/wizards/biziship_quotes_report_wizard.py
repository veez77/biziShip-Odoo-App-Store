from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class BizishipQuotesReportExportWizard(models.TransientModel):
    _name = 'biziship.quotes.report.export.wizard'
    _description = 'BiziShip Quotes Report — Export'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    po_number = fields.Char(string='PO Number', readonly=True)
    markup_enabled = fields.Boolean(string="Markup Available", readonly=True, default=False)
    markup_rule_description = fields.Char(string="Markup Rule", readonly=True)
    apply_markup = fields.Boolean(
        string="Apply Markup",
        default=False,
        help="Add company markup to carrier prices"
    )
    html_report = fields.Html(
        string="Report Preview",
        readonly=True,
        compute='_compute_html_report'
    )

    @api.model
    def default_get(self, fields_list):
        import logging
        _logger = logging.getLogger(__name__)

        result = super().default_get(fields_list)
        sale_order_id = self.env.context.get('default_sale_order_id')
        if sale_order_id:
            result['sale_order_id'] = sale_order_id
            so = self.env['sale.order'].browse(sale_order_id)
            result['po_number'] = so.biziship_po_number or ''

            # Fetch markup config from backend (non-fatal)
            from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

            markup_config = QuotesMarkup.get_company_markup_config(self.env)
            _logger.info(f"ExportWizard default_get: markup_config={markup_config}, user_email={self.env.user.email}, biziship_email={self.env.user.biziship_email}, has_token={bool(self.env.user.biziship_token)}")

            if markup_config and markup_config.get('enabled'):
                result['markup_enabled'] = True
                result['markup_rule_description'] = QuotesMarkup.format_markup_description(markup_config)
            else:
                _logger.info(f"ExportWizard: markup not enabled or config is None")

        return result

    @api.depends('sale_order_id')
    def _compute_html_report(self):
        from odoo.addons.biziship.models.quotes_report_generator import QuotesReportGenerator

        for rec in self:
            if not rec.sale_order_id:
                rec.html_report = False
                continue

            so = rec.sale_order_id
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

            # Fetch markup config if user wants to apply it
            markup_config = None
            if self.apply_markup and self.markup_enabled:
                from odoo.addons.biziship.models.quotes_markup import QuotesMarkup
                markup_config = QuotesMarkup.get_company_markup_config(self.env)

            try:
                html = QuotesReportGenerator.generate_quotes_html_report(
                    shipment_data=shipment_data,
                    quotes=quotes,
                    markup_config=markup_config,
                    apply_markup=self.apply_markup and self.markup_enabled
                )
                rec.html_report = html
            except Exception as e:
                _logger.error("Failed to generate quotes report: %s", str(e), exc_info=True)
                rec.html_report = False

    def action_export_report(self):
        import base64
        self.ensure_one()

        if not self.sale_order_id or not self.sale_order_id.biziship_quote_ids:
            raise UserError(_("No quotes to export."))

        from odoo.addons.biziship.models.quotes_report_generator import QuotesReportGenerator

        so = self.sale_order_id

        # Build shipment data
        shipment_data = {
            'request_id': str(so.id),
            'po_number': self.po_number or '',
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

        # Fetch markup config if user wants to apply it
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

        markup_config = None
        if self.apply_markup and self.markup_enabled:
            markup_config = QuotesMarkup.get_company_markup_config(self.env)

        # Generate HTML directly (bypasses Html field sanitization)
        html_content = QuotesReportGenerator.generate_quotes_html_report(
            shipment_data=shipment_data,
            quotes=quotes,
            markup_config=markup_config,
            apply_markup=self.apply_markup and self.markup_enabled
        )

        so_id_short = str(so.id)[:8]
        today = datetime.now().strftime('%Y%m%d')
        filename = f"biziship-quotes-{so_id_short}-{today}.html"

        # Encode the HTML content as base64 for download
        html_bytes = html_content.encode('utf-8')
        b64_content = base64.b64encode(html_bytes).decode('utf-8')

        # Create attachment with proper mimetype
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': b64_content,
            'mimetype': 'text/html',
            'res_model': self._name,
            'res_id': self.id,
        })

        # Trigger download and close dialog
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
            'close': True,
        }


class BizishipQuotesReportEmailWizard(models.TransientModel):
    _name = 'biziship.quotes.report.email.wizard'
    _description = 'BiziShip Quotes Report — Email'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    markup_enabled = fields.Boolean(string="Markup Available", readonly=True, default=False)
    markup_rule_description = fields.Char(string="Markup Rule", readonly=True)
    apply_markup = fields.Boolean(
        string="Apply Company Markup",
        default=False,
        help="Mark up carrier prices with your company's margin rule before sharing"
    )
    to_emails = fields.Char(
        string="Recipients (comma-separated)",
        help="Email addresses to send the report to"
    )
    html_report = fields.Html(
        string="Report Preview",
        readonly=True,
        compute='_compute_html_report'
    )
    markup_preview_html = fields.Html(
        string="Markup Preview",
        readonly=True,
        compute='_compute_markup_preview'
    )

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        sale_order_id = self.env.context.get('default_sale_order_id')
        if sale_order_id:
            result['sale_order_id'] = sale_order_id
            from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

            markup_config = QuotesMarkup.get_company_markup_config(self.env)
            if markup_config and markup_config.get('enabled'):
                result['markup_enabled'] = True
                result['markup_rule_description'] = QuotesMarkup.format_markup_description(markup_config)

        return result

    @api.depends('sale_order_id', 'apply_markup')
    def _compute_html_report(self):
        from odoo.addons.biziship.models.quotes_report_generator import QuotesReportGenerator
        from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

        for rec in self:
            if not rec.sale_order_id:
                rec.html_report = False
                continue

            so = rec.sale_order_id
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

            markup_config = None
            if rec.apply_markup and rec.markup_enabled:
                markup_config = QuotesMarkup.get_company_markup_config(self.env)

            try:
                html = QuotesReportGenerator.generate_quotes_html_report(
                    shipment_data=shipment_data,
                    quotes=quotes,
                    markup_config=markup_config,
                    apply_markup=rec.apply_markup and rec.markup_enabled
                )
                rec.html_report = html
            except Exception as e:
                _logger.error("Failed to generate quotes report: %s", str(e), exc_info=True)
                rec.html_report = False

    @api.depends('sale_order_id', 'apply_markup', 'markup_enabled')
    def _compute_markup_preview(self):
        for rec in self:
            if not rec.apply_markup or not rec.markup_enabled:
                rec.markup_preview_html = False
                continue

            so = rec.sale_order_id
            if not so or not so.biziship_quote_ids:
                rec.markup_preview_html = False
                continue

            from odoo.addons.biziship.models.quotes_markup import QuotesMarkup

            markup_config = QuotesMarkup.get_company_markup_config(self.env)
            if not markup_config or not markup_config.get('enabled'):
                rec.markup_preview_html = False
                continue

            rows = []
            for quote in so.biziship_quote_ids:
                original = quote.total_charge
                if original is None:
                    continue

                marked_up = QuotesMarkup.apply_markup(original, markup_config)
                delta = marked_up - original

                rows.append(f"""<tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{quote.carrier_name}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right;"><strong>${original:,.2f}</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right; color: #1a6e3c;"><strong>${marked_up:,.2f}</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right; color: #666;">+${delta:,.2f}</td>
                </tr>""")

            rule_desc = QuotesMarkup.format_markup_description(markup_config)

            html = f"""<div style="margin: 16px 0; padding: 16px; background: #f0f4fc; border-radius: 8px; border-left: 4px solid #1a3c6e;">
                <div style="font-weight: 600; margin-bottom: 12px; color: #1a3c6e;">Markup Preview</div>
                <div style="font-size: 12px; margin-bottom: 12px; color: #666;">{rule_desc}</div>
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    <thead>
                        <tr style="background: #e8eef7;">
                            <th style="padding: 8px; text-align: left; font-weight: 600;">Carrier</th>
                            <th style="padding: 8px; text-align: right; font-weight: 600;">Original Price</th>
                            <th style="padding: 8px; text-align: right; font-weight: 600;">With Markup</th>
                            <th style="padding: 8px; text-align: right; font-weight: 600;">Fee</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>"""

            rec.markup_preview_html = html

    def action_send_report(self):
        self.ensure_one()

        if not self.to_emails:
            raise UserError(_("Please enter at least one recipient email address."))

        if not self.html_report:
            raise UserError(_("No report to send. Please ensure quotes are loaded."))

        emails_raw = self.to_emails.split(',')
        emails = [e.strip() for e in emails_raw if e.strip()]

        if not emails:
            raise UserError(_("Please enter at least one valid email address."))

        if not self.env.user.biziship_token:
            raise UserError(_("You must be logged in to BiziShip to send reports. Please connect your BiziShip account first."))

        try:
            import requests
            from odoo.addons.biziship.api_utils import get_biziship_api_url

            api_url = get_biziship_api_url(self.env)
            request_id = self.sale_order_id.id
            url = f"{api_url.rstrip('/')}/erp/quote/{request_id}/email-report"

            headers = {
                "Authorization": f"Bearer {self.env.user.biziship_token}",
                "Content-Type": "application/json",
            }

            payload = {
                "to_emails": emails,
                "html_report": self.html_report,
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 403:
                try:
                    error_data = response.json()
                    blocked_emails = error_data.get('blocked_emails', [])
                    unverified_emails = error_data.get('unverified_emails', [])
                    detail = error_data.get('detail', 'Access denied')

                    msg_parts = [detail]
                    if blocked_emails:
                        msg_parts.append(f"Blocked: {', '.join(blocked_emails)}")
                    if unverified_emails:
                        msg_parts.append(f"Unverified: {', '.join(unverified_emails)}")

                    raise UserError(_("\n".join(msg_parts)))
                except ValueError:
                    raise UserError(_("Access denied. Please check your email list."))

            if response.status_code in [200, 201]:
                response_data = response.json()
                shared_link = response_data.get('shared_link', '')
                message = _("Report sent successfully to: %s") % ', '.join(emails)
                if shared_link:
                    message += f"\n\nShared link: {shared_link}"

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Email Sent'),
                        'message': message,
                        'sticky': False,
                        'type': 'success',
                    }
                }

            try:
                error_json = response.json()
                error_msg = error_json.get('detail', error_json.get('message', str(response.status_code)))
            except ValueError:
                error_msg = response.text or str(response.status_code)

            raise UserError(_("Failed to send report: %s") % error_msg)

        except requests.exceptions.Timeout:
            raise UserError(_("Request timed out. The server took too long to respond. Please try again."))
        except requests.exceptions.ConnectionError:
            raise UserError(_("Failed to connect to BiziShip API. Please check your connection and try again."))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Network error: %s") % str(e))
        except UserError:
            raise
        except Exception as e:
            _logger.error("Unexpected error in action_send_report: %s", str(e))
            raise UserError(_("An unexpected error occurred: %s") % str(e))
