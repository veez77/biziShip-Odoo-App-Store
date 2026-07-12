import json
import requests
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.biziship.api_utils import get_biziship_api_url, get_erp_api_key

_logger = logging.getLogger(__name__)

TZ_OFFSET_HOURS = -5  # EST (UTC-5); close enough for display without pytz dependency


def _fmt_utc_to_est(utc_str):
    """Convert ISO UTC timestamp (with Z or offset) to Eastern Time display string."""
    if not utc_str:
        return ''
    try:
        s = utc_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
        ts = dt.timestamp() + TZ_OFFSET_HOURS * 3600
        local = datetime.utcfromtimestamp(ts)
        return local.strftime('%b %d, %Y %I:%M %p ET')
    except Exception:
        return utc_str


def _fmt_local_ts(ts_str):
    """Format a local (no-timezone) ISO timestamp for display."""
    if not ts_str:
        return ''
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime('%b %d, %Y %I:%M %p')
    except Exception:
        return ts_str


class BizishipTrackingWizard(models.TransientModel):
    _name = 'biziship.tracking.wizard'
    _description = 'BiziShip Shipment Tracking'

    sale_order_id = fields.Many2one('sale.order', readonly=True)
    bol_number = fields.Char(readonly=True)

    # Persistent data (mirrored back to sale.order on refresh)
    tracking_status = fields.Char(readonly=True)
    pro_number = fields.Char(readonly=True)
    last_updated = fields.Char(readonly=True)

    # Rendered header with copy buttons (sanitize=False to allow onclick)
    header_html = fields.Html(compute='_compute_header_html', sanitize=False)

    # Transient display fields
    events_html = fields.Html(readonly=True)
    tracking_history_json = fields.Text()  # raw events stored for Analyze Journey call
    has_tracking_events = fields.Boolean(default=False)
    error_message = fields.Char(readonly=True)
    is_loading = fields.Boolean(default=False)

    # AI Journey fields
    ai_summary_html = fields.Html(readonly=True)
    ai_error_message = fields.Char(readonly=True)
    ai_is_loading = fields.Boolean(default=False)
    show_ai_panel = fields.Boolean(default=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        so_id = self.env.context.get('active_id')
        if so_id:
            so = self.env['sale.order'].browse(so_id)
            res['sale_order_id'] = so_id
            res['bol_number'] = so.biziship_bol_number or ''
            # Pre-populate last-known values so user sees prior state immediately
            # These get refreshed when user clicks "Refresh"
            if so.biziship_tracking_status:
                res['tracking_status'] = so.biziship_tracking_status
                res['pro_number'] = so.biziship_pro_number or ''
                res['last_updated'] = so.biziship_last_tracked_at or ''
        return res

    @api.depends('bol_number', 'pro_number', 'tracking_status', 'last_updated')
    def _compute_header_html(self):
        copy_style = (
            "background:none;border:none;cursor:pointer;font-size:13px;"
            "padding:0 3px;color:#aaa;vertical-align:middle;line-height:1;"
        )
        for rec in self:
            bol = rec.bol_number or ''
            pro = rec.pro_number or ''
            status = rec.tracking_status or ''
            updated = rec.last_updated or ''

            bol_copy = (
                f'<button onclick="navigator.clipboard.writeText(\'{bol}\');this.textContent=\'✅\';'
                f'setTimeout(()=>this.textContent=\'📋\',1500);return false;" '
                f'title="Copy BOL number" style="{copy_style}">📋</button>'
            ) if bol else ''

            pro_copy = (
                f'<button onclick="navigator.clipboard.writeText(\'{pro}\');this.textContent=\'✅\';'
                f'setTimeout(()=>this.textContent=\'📋\',1500);return false;" '
                f'title="Copy PRO number" style="{copy_style}">📋</button>'
            ) if pro else ''

            status_html = (
                f'<span style="display:inline-block;background:#e8f5e9;color:#1b7a40;font-weight:700;'
                f'font-size:13px;border-radius:20px;padding:4px 16px;border:1px solid #a5d6a7;">{status}</span>'
            ) if status else '<span style="color:#aaa;font-size:13px;">—</span>'

            updated_html = (
                f'<div style="font-size:11px;color:#aaa;margin-top:6px;">Last updated: {updated}</div>'
            ) if updated else ''

            pro_row = (
                f'<div style="margin-top:10px;">'
                f'  <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:#888;letter-spacing:0.7px;">PRO #</span>'
                f'  <div style="font-size:14px;font-weight:600;color:#1a1a2e;margin-top:2px;">{pro}{pro_copy}</div>'
                f'</div>'
            ) if pro else ''

            rec.header_html = (
                f'<div style="margin-bottom:16px;padding-bottom:14px;border-bottom:2px solid #e8f5e9;">'
                f'  <div style="display:flex;align-items:flex-start;justify-content:space-between;">'
                f'    <div style="flex:1;">'
                f'      <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:#888;letter-spacing:0.8px;">BOL Number</span>'
                f'      <div style="font-size:17px;font-weight:700;color:#1a1a2e;margin-top:3px;">{bol}{bol_copy}</div>'
                f'    </div>'
                f'    <div style="flex-shrink:0;margin-left:16px;margin-top:2px;">{status_html}</div>'
                f'  </div>'
                f'  {pro_row}'
                f'  {updated_html}'
                f'</div>'
            )

    def _get_api_headers(self):
        erp_key = get_erp_api_key(self.env)
        user = self.env.user
        email = (
            user.biziship_email
            if user.biziship_token and user.biziship_email
            else user.email
        ) or ''
        headers = {
            'X-ERP-API-Key': erp_key,
            'X-User-Email': email,
            'Content-Type': 'application/json',
        }
        if user.biziship_token:
            headers['Authorization'] = f'Bearer {user.biziship_token}'
        return headers

    def _fetch_tracking_data(self):
        """Call /erp/tracking/status and write results to self. Returns True on success."""
        if not self.bol_number:
            self.write({'error_message': 'No BOL number found on this shipment.'})
            return False

        base_url = get_biziship_api_url(self.env).rstrip('/')
        url = f'{base_url}/erp/tracking/status'
        headers = self._get_api_headers()
        payload = {'bol': self.bol_number}

        _logger.warning('BiziShip tracking — URL: %s', url)
        _logger.warning('BiziShip tracking — Headers: %s', json.dumps({k: (v[:12] + '…' if k == 'Authorization' else v) for k, v in headers.items()}))
        _logger.warning('BiziShip tracking — Body: %s', json.dumps(payload))
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            _logger.warning('BiziShip tracking — Response status: %s', resp.status_code)
            _logger.warning('BiziShip tracking — Response body: %s', resp.text[:1000])
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.HTTPError as e:
            msg = f'Tracking API error: {e.response.status_code} – {e.response.text[:500]}'
            _logger.error('BiziShip tracking HTTP error: %s', msg)
            self.write({'error_message': msg})
            return False
        except requests.exceptions.RequestException as e:
            msg = f'Could not reach tracking service: {str(e)}'
            _logger.error('BiziShip tracking request error: %s', msg)
            self.write({'error_message': msg})
            return False

        status = data.get('trackingStatus') or data.get('status') or 'Unknown'
        pro = data.get('proNumber') or data.get('pro_number') or ''
        # API returns lastTrackedAt; fall back to lastUpdated
        updated_raw = data.get('lastTrackedAt') or data.get('lastUpdated') or data.get('last_updated') or ''
        updated_display = _fmt_utc_to_est(updated_raw)
        # API returns trackingHistory; fall back to other possible keys
        events = data.get('trackingHistory') or data.get('trackingEvents') or data.get('events') or []

        self.write({
            'tracking_status': status,
            'pro_number': pro,
            'last_updated': updated_display,
            'events_html': self._build_events_html(events),
            'tracking_history_json': json.dumps(events),
            'has_tracking_events': bool(events),
            'error_message': False,
        })

        # Persist summary fields back to sale.order
        self.sale_order_id.sudo().write({
            'biziship_tracking_status': status,
            'biziship_pro_number': pro,
            'biziship_last_tracked_at': updated_display,
        })
        return True

    def action_refresh_tracking(self):
        self.ensure_one()
        self._fetch_tracking_data()
        return self._reopen()

    def action_analyze_journey(self):
        self.ensure_one()
        if not self.bol_number:
            self.ai_error_message = 'No BOL number found on this shipment.'
            return self._reopen()

        base_url = get_biziship_api_url(self.env).rstrip('/')
        url = f'{base_url}/erp/tracking/summary'
        headers = self._get_api_headers()
        history = json.loads(self.tracking_history_json) if self.tracking_history_json else []
        so = self.sale_order_id
        origin_parts = [p for p in [so.biziship_origin_city, so.biziship_origin_state_id.code if so.biziship_origin_state_id else '', so.biziship_origin_zip] if p]
        dest_parts = [p for p in [so.biziship_dest_city, so.biziship_dest_state_id.code if so.biziship_dest_state_id else '', so.biziship_dest_zip] if p]
        payload = {
            'bol': self.bol_number,
            'history': history,
            'origin': ', '.join(origin_parts),
            'destination': ', '.join(dest_parts),
        }

        try:
            _logger.info('BiziShip journey analysis request: %s', json.dumps(payload))
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            _logger.info('BiziShip journey analysis response: %s', json.dumps(data))
        except requests.exceptions.HTTPError as e:
            self.write({
                'ai_error_message': f'Analysis API error: {e.response.status_code} – {e.response.text[:200]}',
                'show_ai_panel': True,
            })
            return self._reopen()
        except requests.exceptions.RequestException as e:
            self.write({
                'ai_error_message': f'Could not reach analysis service: {str(e)}',
                'show_ai_panel': True,
            })
            return self._reopen()

        ai_html = self._build_ai_summary_html(data)
        self.write({
            'ai_summary_html': ai_html,
            'ai_error_message': False,
            'show_ai_panel': True,
        })
        return self._reopen()

    def _build_events_html(self, events):
        if not events:
            return '<p class="text-muted" style="font-size:13px;">No tracking events available yet.</p>'

        # Sort newest-first by timestamp
        def _ev_sort_key(e):
            return e.get('timeStamp') or e.get('timestamp') or ''
        sorted_events = sorted(events, key=_ev_sort_key, reverse=True)

        rows = []
        for ev in sorted_events:
            # API field names: timeStamp, statusReason, status, city, state
            ts_raw = ev.get('timeStamp') or ev.get('timestamp') or ev.get('date') or ''
            ts = _fmt_local_ts(ts_raw) if ts_raw else ''
            city = ev.get('city') or ''
            state = ev.get('state') or ''
            location_parts = [p for p in [city, state] if p]
            location = ', '.join(location_parts)
            description = ev.get('statusReason') or ev.get('description') or ev.get('event') or ''
            status_code = ev.get('status') or ev.get('statusCode') or ev.get('code') or ''

            desc_lower = (description + ' ' + status_code).lower()
            icon = '📦'
            if 'delivered' in desc_lower or 'consignee' in desc_lower or status_code.lower() == 'completed':
                icon = '✅'
            elif 'picked up' in desc_lower or 'pickup' in desc_lower or 'actual pickup' in desc_lower:
                icon = '🚚'
            elif 'departed' in desc_lower or 'in transit' in desc_lower:
                icon = '🛣️'
            elif 'delay' in desc_lower or 'exception' in desc_lower or 'not completed' in desc_lower:
                icon = '⚠️'
            elif 'arrived' in desc_lower or 'at stop' in desc_lower or 'terminal' in desc_lower:
                icon = '🏭'

            location_html = f'<span style="color:#6c757d;font-size:11px;margin-left:8px;">📍 {location}</span>' if location else ''
            code_html = f'<span style="color:#adb5bd;font-size:10px;margin-left:6px;">[{status_code}]</span>' if status_code else ''

            rows.append(
                f'<div style="display:flex;align-items:flex-start;padding:10px 0;border-bottom:1px solid #f0f0f0;">'
                f'  <div style="font-size:18px;margin-right:12px;min-width:26px;text-align:center;">{icon}</div>'
                f'  <div style="flex:1;">'
                f'    <div style="font-size:13px;font-weight:600;color:#1a1a2e;">{description}{code_html}</div>'
                f'    <div style="margin-top:2px;">'
                f'      <span style="font-size:11px;color:#888;">{ts}</span>{location_html}'
                f'    </div>'
                f'  </div>'
                f'</div>'
            )

        return (
            '<div style="max-height:320px;overflow-y:auto;padding-right:4px;">'
            + ''.join(rows)
            + '</div>'
        )

    def _render_bullets(self, items):
        if not items:
            return ''
        lis = ''.join(f'<li style="margin-bottom:4px;">{item}</li>' for item in items)
        return f'<ul style="margin:6px 0 0 16px;padding:0;font-size:13px;color:#1a1a2e;line-height:1.6;">{lis}</ul>'

    def _build_ai_summary_html(self, data):
        sections = []
        label_style = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#6c757d;letter-spacing:0.8px;margin-bottom:6px;'
        wrap_style = 'margin-bottom:16px;'

        # --- Current Status ---
        cs = data.get('currentStatus') or data.get('current_status') or ''
        if cs:
            if isinstance(cs, dict):
                emoji = cs.get('emoji', '')
                label = cs.get('label', '')
                bullets = cs.get('bullets') or []
                body = (
                    f'<div style="font-size:14px;font-weight:700;color:#1a1a2e;">{emoji} {label}</div>'
                    + self._render_bullets(bullets)
                )
            else:
                body = f'<div style="font-size:13px;color:#1a1a2e;line-height:1.6;">{cs}</div>'
            sections.append(f'<div style="{wrap_style}"><div style="{label_style}">📍 Current Status</div>{body}</div>')

        # --- Timeline ---
        tl = data.get('timeline') or data.get('journey') or []
        if tl:
            if isinstance(tl, list):
                phase_html = ''
                for phase in tl:
                    p_emoji = phase.get('emoji', '')
                    p_date = phase.get('dateLabel', '')
                    p_label = phase.get('phaseLabel', '')
                    events = phase.get('events') or []
                    ev_rows = ''
                    for ev in events:
                        t = ev.get('time', '')
                        title = ev.get('title', '')
                        note = ev.get('note', '')
                        ev_rows += (
                            f'<div style="margin-bottom:6px;">'
                            f'  <span style="font-size:11px;color:#888;min-width:90px;display:inline-block;">{t}</span>'
                            f'  <strong style="font-size:13px;">{title}</strong>'
                            + (f'<div style="font-size:12px;color:#555;margin-left:94px;margin-top:1px;">{note}</div>' if note else '')
                            + '</div>'
                        )
                    phase_html += (
                        f'<div style="margin-bottom:10px;padding:8px 10px;background:#fff;border-radius:6px;border:1px solid #e9ecef;">'
                        f'  <div style="font-size:12px;font-weight:700;color:#1a1a2e;margin-bottom:6px;">{p_emoji} {p_date} — {p_label}</div>'
                        f'  {ev_rows}'
                        f'</div>'
                    )
                body = phase_html
            else:
                body = f'<div style="font-size:13px;color:#1a1a2e;line-height:1.6;">{tl}</div>'
            sections.append(f'<div style="{wrap_style}"><div style="{label_style}">🗓️ Timeline</div>{body}</div>')

        # --- What This Means ---
        wtm = data.get('whatThisMeans') or data.get('what_this_means') or data.get('analysis') or ''
        if wtm:
            if isinstance(wtm, dict):
                bullets = wtm.get('bullets') or []
                flow = wtm.get('flow') or []
                flow_html = ''
                if flow:
                    steps = ' → '.join(
                        f'<strong>{s}</strong>' if i == (len(flow) - 1) else s
                        for i, s in enumerate(flow)
                    )
                    flow_html = f'<div style="font-size:12px;color:#555;margin-top:6px;">Stage: {steps}</div>'
                body = self._render_bullets(bullets) + flow_html
            else:
                body = f'<div style="font-size:13px;color:#1a1a2e;line-height:1.6;">{wtm}</div>'
            sections.append(f'<div style="{wrap_style}"><div style="{label_style}">💡 What This Means</div>{body}</div>')

        # --- What Happens Next ---
        whn = data.get('whatHappensNext') or data.get('what_happens_next') or data.get('next_steps') or ''
        if whn:
            if isinstance(whn, list):
                body = self._render_bullets(whn)
            else:
                body = f'<div style="font-size:13px;color:#1a1a2e;line-height:1.6;">{whn}</div>'
            sections.append(f'<div style="{wrap_style}"><div style="{label_style}">🔮 What Happens Next</div>{body}</div>')

        # --- Fallback plain summary ---
        if not sections:
            summary = data.get('summary') or ''
            if summary:
                sections.append(f'<div style="font-size:13px;color:#1a1a2e;line-height:1.6;">{summary}</div>')
            else:
                return '<p style="color:#6c757d;font-size:13px;">No AI analysis available for this shipment.</p>'

        return (
            '<div style="background:#f8f9fa;border-radius:8px;padding:16px;border-left:4px solid #00b14f;">'
            + ''.join(sections)
            + '</div>'
        )

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'biziship.tracking.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
