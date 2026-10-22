import base64
import html
import io
import json
import logging
from urllib.parse import quote

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from odoo.addons.biziship import api_utils
from odoo.addons.biziship.api_utils import get_erp_api_key, BIZISHIP_APP_NAME, BIZISHIP_MODULE_VERSION

_logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = int(4.5 * 1024 * 1024)  # ~4.5 MB, the gateway's effective per-photo cap
DOWNSCALE_LONG_EDGE = 1600
DOWNSCALE_JPEG_QUALITY = 85


class BizishipPalletLine(models.TransientModel):
    _name = 'biziship.pallet.line'
    _description = 'BiziShip Shipment Pallet (transient display row)'

    wizard_id = fields.Many2one('biziship.pallet.photos.wizard', required=True, ondelete='cascade')
    pallet_uuid = fields.Char(string='Pallet ID')
    name = fields.Char(string='Pallet Name')
    photos_json = fields.Text(string='Photos (raw)')
    photo_count = fields.Integer(string='# Photos', compute='_compute_photo_count')
    photos_html = fields.Html(string='Photos', compute='_compute_photos_html', sanitize=False)

    def _photos(self):
        self.ensure_one()
        if not self.photos_json:
            return []
        try:
            return json.loads(self.photos_json)
        except Exception:
            return []

    @api.depends('photos_json')
    def _compute_photo_count(self):
        for line in self:
            line.photo_count = len(line._photos())

    def _photo_cells_html(self):
        """The <div> per photo (thumbnail + view/download/delete). Shared by
        photos_html (kept for debugging) and the wizard-level all_photos_html -
        the latter is what's actually shown, since a plain form-level Html field
        doesn't go through the list/tree renderer's cell-tooltip logic that was
        dumping this field's raw source as a tooltip when it lived in a <tree>
        column (see biziship.pallet.photos.wizard._compute_all_photos_html)."""
        self.ensure_one()
        cells = []
        for photo in self._photos():
            image_id = photo.get('id', '')
            url = photo.get('url', '')
            filename = quote(f"{image_id}.jpg")
            download_url = f"/biziship/image_proxy?url={quote(url, safe='')}&filename={filename}"
            size_bytes = photo.get('sizeBytes') or 0
            size_label = f"{size_bytes / 1024:.0f} KB" if size_bytes else ''
            cells.append(f'''
                <div class="biziship-pallet-photo-thumb-wrap" data-image-id="{image_id}" data-line-id="{self.id}">
                    <a href="{url}" target="_blank" class="biziship-pallet-photo-view">
                        <img class="biziship-pallet-photo-thumb" src="{url}"/>
                    </a>
                    <a href="#" class="biziship-pallet-photo-delete" title="Delete photo">×</a>
                    <a href="{download_url}" class="biziship-pallet-photo-download" title="Download this photo">⬇</a>
                    <div class="biziship-pallet-photo-size">{size_label}</div>
                </div>
            ''')
        return "".join(cells)

    @api.depends('photos_json')
    def _compute_photos_html(self):
        for line in self:
            cells = line._photo_cells_html()
            if not cells:
                line.photos_html = '<span class="text-muted fst-italic">No photos yet</span>'
            else:
                line.photos_html = f'<div class="biziship-pallet-photo-grid">{cells}</div>'

    @api.onchange('name')
    def _onchange_name_autosave(self):
        """Renames on the gateway as soon as the user leaves the field (blur/Enter/
        tab to the next cell) - standard Odoo editable-tree onchange timing - so no
        separate Save button is needed. Deliberately doesn't call
        wizard_id._populate_pallets() afterward: that unlinks and recreates every
        line (see its docstring), which would delete the very line this onchange
        is running on, out from under itself, same class of bug already hit once
        with the upload wizard's cascade delete."""
        for line in self:
            if not line.pallet_uuid:
                continue
            new_name = (line.name or '').strip()
            if not new_name:
                continue
            line.wizard_id._gateway_request(
                'PATCH', f"pallets/{line.pallet_uuid}", json_body={"name": new_name}
            )

    def action_delete_pallet(self):
        self.ensure_one()
        self.wizard_id._gateway_request('DELETE', f"pallets/{self.pallet_uuid}")
        self.wizard_id._populate_pallets()
        return True

    def action_open_upload_dialog(self):
        """Opens a small standalone popup for the actual file picker + Upload
        button, rather than embedding them in this one2many's tree row - Binary
        fields inside an editable tree row don't reliably commit their value
        before a sibling button's click fires, so action_upload_photo would see
        an empty upload_file half the time. The BOL wizard avoids this same trap
        by keeping its Binary field + button on one standalone form; same fix
        here, just scoped to one pallet via pallet_line_id."""
        self.ensure_one()
        wizard = self.env['biziship.pallet.photo.upload.wizard'].create({'pallet_line_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Upload Photo',
            'res_model': 'biziship.pallet.photo.upload.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _upload_photo(self, upload_file, upload_filename):
        """Shared by the upload popup: resize, size-check, POST, refresh."""
        self.ensure_one()
        if len(self._photos()) >= 3:
            raise UserError(_("This pallet already has the maximum of 3 images."))

        raw_bytes = base64.b64decode(upload_file)
        filename = upload_filename or 'photo.jpg'
        content_bytes, mimetype = self._prepare_image(raw_bytes, filename)

        if len(content_bytes) > MAX_UPLOAD_BYTES:
            raise UserError(_(
                "This photo is still over 4.5 MB after downscaling. Please choose a smaller photo."
            ))

        self.wizard_id._gateway_request(
            'POST', f"pallets/{self.pallet_uuid}/images",
            files={"file": (filename, content_bytes, mimetype)},
        )
        self.wizard_id._populate_pallets()

    def _prepare_image(self, raw_bytes, filename):
        """Downscale to ~1600px long edge / JPEG q85 via Pillow. Falls back to the
        original bytes untouched if Pillow can't open the file (e.g. HEIC without a
        HEIF plugin installed) - the gateway's own 400 'detail' will surface via
        _gateway_request in that case, which is an explicitly accepted fallback."""
        try:
            from PIL import Image
        except ImportError:
            return raw_bytes, 'application/octet-stream'

        try:
            img = Image.open(io.BytesIO(raw_bytes))
            img.load()
        except Exception:
            _logger.info("BiziShip: could not open upload with Pillow (format not supported client-side), "
                         "sending original bytes as-is for %s", filename)
            return raw_bytes, 'application/octet-stream'

        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        long_edge = max(img.size)
        if long_edge > DOWNSCALE_LONG_EDGE:
            scale = DOWNSCALE_LONG_EDGE / float(long_edge)
            new_size = (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale)))
            img = img.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=DOWNSCALE_JPEG_QUALITY)
        return buf.getvalue(), 'image/jpeg'

    def action_delete_photo_by_id(self, image_id):
        """Called via RPC from the click-delegated delete-x in photos_html."""
        self.ensure_one()
        self.wizard_id._gateway_request('DELETE', f"images/{image_id}")
        self.wizard_id._populate_pallets()
        return True

    def action_download_zip(self):
        self.ensure_one()
        return self.wizard_id._zip_download_action(pallet_uuid=self.pallet_uuid)


class BizishipPalletPhotoUploadWizard(models.TransientModel):
    _name = 'biziship.pallet.photo.upload.wizard'
    _description = 'Upload a Pallet Photo'

    # Plain Integer, not a Many2one: _upload_photo() below triggers a full
    # unlink+recreate refresh of every biziship.pallet.line (see
    # _populate_pallets), and a real FK with ondelete='cascade' would cascade-
    # delete THIS record the instant that refresh unlinks the line it points
    # to - out from under the very action_upload() call still running on it,
    # which Odoo then can't re-read afterward ("Record does not exist").
    pallet_line_id = fields.Integer(required=True)
    upload_file = fields.Binary(string='Photo', required=True)
    upload_filename = fields.Char(string='File Name')

    def action_upload(self):
        self.ensure_one()
        if not self.upload_file:
            raise UserError(_("Please choose a photo to upload first."))
        line = self.env['biziship.pallet.line'].browse(self.pallet_line_id)
        parent_wizard_id = line.wizard_id.id
        line._upload_photo(self.upload_file, self.upload_filename)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Shipment Photos',
            'res_model': 'biziship.pallet.photos.wizard',
            'res_id': parent_wizard_id,
            'view_mode': 'form',
            'target': 'new',
        }


class BizishipPalletPhotosWizard(models.TransientModel):
    _name = 'biziship.pallet.photos.wizard'
    _description = 'BiziShip Shipment Photos'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    pallet_line_ids = fields.One2many('biziship.pallet.line', 'wizard_id', string='Pallets')
    new_pallet_name = fields.Char(string='New Pallet Name')
    status_message = fields.Char(string='Status', readonly=True)
    all_photos_html = fields.Html(string='Photos', compute='_compute_all_photos_html', sanitize=False)

    @api.depends('pallet_line_ids.photos_json', 'pallet_line_ids.name')
    def _compute_all_photos_html(self):
        for wizard in self:
            sections = []
            for line in wizard.pallet_line_ids:
                cells = line._photo_cells_html()
                body = (
                    f'<div class="biziship-pallet-photo-grid">{cells}</div>' if cells
                    else '<span class="text-muted fst-italic">No photos yet</span>'
                )
                safe_name = html.escape(line.name or 'Pallet')
                sections.append(f'''
                    <div class="biziship-pallet-photo-section">
                        <div class="biziship-pallet-photo-section-title">{safe_name}</div>
                        {body}
                    </div>
                ''')
            wizard.all_photos_html = "".join(sections) or ''

    # ------------------------------------------------------------------
    # Gateway plumbing
    # ------------------------------------------------------------------
    def _headers(self):
        user = self.env.user
        email = (
            user.biziship_email if user.biziship_token and user.biziship_email else user.email
        ) or ""
        headers = {
            "X-ERP-API-Key": get_erp_api_key(self.env),
            "X-User-Email": email,
            "X-Client-App": BIZISHIP_APP_NAME,
            "X-Client-Version": BIZISHIP_MODULE_VERSION,
        }
        if user.biziship_token:
            headers["Authorization"] = f"Bearer {user.biziship_token}"
        return headers

    def _get_shipment_id(self):
        """The pallets/photos gateway wants the shipment UUID. Despite its name,
        sale.order.biziship_shipment_id actually holds a plain numeric reference
        number (from /erp/book's 'shipment_id' key); the real UUID is written to
        biziship_booking_id (from /erp/book's 'biziship_id' key) - confirmed by
        inspecting a real booked order's stored values."""
        self.ensure_one()
        order = self.sale_order_id
        if order.biziship_booking_id:
            return order.biziship_booking_id

        if not order.biziship_bol_number:
            raise UserError(_("This shipment hasn't been booked yet."))

        base_url = api_utils.get_biziship_api_url(self.env)
        url = f"{base_url}/erp/shipments"
        try:
            response = requests.get(
                url, headers=self._headers(),
                params={"bolNumber": order.biziship_bol_number, "limit": 1},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            _logger.exception("BiziShip: failed to resolve shipment ID from BOL number")
            raise UserError(_("Could not look up this shipment on BiziShip: %s") % str(e))

        items = data.get('items') or data.get('data') or data.get('results') or data
        if not items:
            raise UserError(_("No BiziShip shipment found for BOL number %s.") % order.biziship_bol_number)

        shipment_id = items[0].get('id')
        if not shipment_id:
            raise UserError(_("BiziShip's shipment lookup response was missing an id."))

        order.biziship_booking_id = shipment_id
        return shipment_id

    def _gateway_request(self, method, path, json_body=None, files=None):
        """Thin wrapper for every /erp/shipments/:id/... call this wizard needs.
        Surfaces the gateway's own 400/409 'detail' verbatim; everything else becomes
        a generic message (with the real response logged for debugging)."""
        self.ensure_one()
        base_url = api_utils.get_biziship_api_url(self.env)
        shipment_id = self._get_shipment_id()
        url = f"{base_url}/erp/shipments/{shipment_id}/{path}"

        headers = self._headers()
        try:
            response = requests.request(
                method, url, headers=headers, json=json_body, files=files, timeout=20,
            )
        except Exception as e:
            _logger.exception("BiziShip: pallet/photo gateway request failed (%s %s)", method, url)
            raise UserError(_("Could not reach BiziShip right now. Please try again in a moment."))

        if response.status_code in (200, 201, 204):
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

        if response.status_code in (400, 409):
            try:
                detail = response.json().get('detail')
            except Exception:
                detail = None
            raise UserError(detail or _("BiziShip rejected this request."))

        _logger.error(
            "BiziShip: pallet/photo gateway error %s %s -> %s: %s",
            method, url, response.status_code, response.text,
        )
        raise UserError(_("BiziShip is temporarily unavailable (error %s). Please try again shortly.") % response.status_code)

    def _populate_pallets(self):
        self.ensure_one()
        data = self._gateway_request('GET', 'pallets')
        pallets = data.get('pallets', []) if isinstance(data, dict) else []

        self.pallet_line_ids.unlink()
        self.env['biziship.pallet.line'].create([
            {
                'wizard_id': self.id,
                'pallet_uuid': p.get('id'),
                'name': p.get('name') or '',
                'photos_json': json.dumps(p.get('images', [])),
            }
            for p in pallets
        ])
        self.status_message = '' if pallets else _("No pallets yet. Add one to start uploading photos.")
        self.sale_order_id.biziship_photo_count = sum(len(p.get('images', [])) for p in pallets)

    # ------------------------------------------------------------------
    # Wizard-level actions
    # ------------------------------------------------------------------
    def _reopen_action(self):
        """Buttons on the wizard's own root record (unlike one2many line buttons,
        which auto-refresh in place) need to explicitly return an action or Odoo
        treats a plain True/None return as "done, close the dialog"."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Shipment Photos',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_refresh(self):
        self.ensure_one()
        self._populate_pallets()
        return self._reopen_action()

    def action_add_pallet(self):
        self.ensure_one()
        body = {"name": self.new_pallet_name.strip()} if (self.new_pallet_name or '').strip() else {}
        self._gateway_request('POST', 'pallets', json_body=body)
        self.new_pallet_name = False
        self._populate_pallets()
        return self._reopen_action()

    def action_download_zip_all(self):
        self.ensure_one()
        return self._zip_download_action()

    def _zip_download_action(self, pallet_uuid=None):
        self.ensure_one()
        url = f"/biziship/shipments/{self.sale_order_id.id}/pallets/zip"
        if pallet_uuid:
            url += f"?pallet_id={pallet_uuid}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }
