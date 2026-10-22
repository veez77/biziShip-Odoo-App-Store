/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export const BIZISHIP_VERSION = "1.1.1.0";
export const BIZISHIP_RELEASE_DATE = "May 24, 2026";

export class BiziShipVersionDialog extends Component {
    static template = "biziship.VersionDialog";
    static components = { Dialog };
    static props = { close: Function };

    get version() { return BIZISHIP_VERSION; }
    get releaseDate() { return BIZISHIP_RELEASE_DATE; }
}
