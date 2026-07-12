/** @odoo-module **/

/**
 * BiziShip "Shipment notifications" widget for the booking dialog.
 *
 * Bound to a JSON Char field (biziship_cc_emails_json) holding the editable per-shipment
 * recipients as an array of strings. On mount it fetches the company's default recipients
 * from the ERP Gateway (server-side, via ORM) and shows them as read-only chips. The user
 * can add up to 10 extra recipients via a chip input; those are submitted with the booking.
 *
 * The defaults fetch is capped at 6 seconds and never blocks booking — on timeout/failure
 * the defaults list is simply empty.
 */

import { Component, useState, useRef, onWillStart, status } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_CHIPS = 10;
const FETCH_TIMEOUT_MS = 6000;

export class BizishipEmailChips extends Component {
    static template = "biziship.EmailChips";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.inputRef = useRef("input");
        this.max = MAX_CHIPS;
        this.state = useState({
            defaults: [],
            loadingDefaults: true,
            draft: "",
            error: "",
            invalid: false,
        });

        onWillStart(async () => {
            await this._loadDefaults();
        });
    }

    // ---- company default recipients (read-only) ----
    async _loadDefaults() {
        this.state.loadingDefaults = true;
        const timeout = new Promise((resolve) => setTimeout(() => resolve(null), FETCH_TIMEOUT_MS));
        let result = null;
        try {
            result = await Promise.race([
                this.orm.call("biziship.quote.confirm.wizard", "biziship_get_default_cc_emails", []),
                timeout,
            ]);
        } catch (e) {
            result = null;
        }
        // Component may have been destroyed (dialog closed) while awaiting.
        if (status(this) === "destroyed") {
            return;
        }
        this.state.defaults = Array.isArray(result) ? result : [];
        this.state.loadingDefaults = false;
    }

    get hasDefaults() {
        return this.state.defaults.length > 0;
    }

    // ---- salesperson recipient (toggleable, included by default) ----
    get salespersonName() {
        return this.props.record.data.biziship_salesperson_name || "";
    }
    get salespersonEmail() {
        return this.props.record.data.biziship_salesperson_email || "";
    }
    get hasSalesperson() {
        return !!this.salespersonEmail;
    }
    get notifySalesperson() {
        return this.props.record.data.biziship_notify_salesperson;
    }
    toggleSalesperson() {
        this.props.record.update({ biziship_notify_salesperson: !this.notifySalesperson });
    }

    // ---- editable chips (round-trip through the bound JSON field) ----
    get chips() {
        try {
            const v = JSON.parse(this.props.record.data[this.props.name] || "[]");
            return Array.isArray(v) ? v : [];
        } catch (e) {
            return [];
        }
    }

    _commit(chips) {
        this.props.record.update({ [this.props.name]: JSON.stringify(chips) });
    }

    get atMax() {
        return this.chips.length >= this.max;
    }

    get helperText() {
        return `Press Enter or comma to add. ${this.chips.length}/${this.max} addresses.`;
    }

    _focusInput() {
        if (this.inputRef.el) {
            this.inputRef.el.focus();
        }
    }

    _addEmail(raw) {
        const email = (raw || "").trim();
        if (!email) {
            return true; // silently ignore empty
        }
        if (this.chips.length >= this.max) {
            this.state.error = `Maximum ${this.max} addresses allowed.`;
            this.state.invalid = true;
            return false;
        }
        if (!EMAIL_RE.test(email)) {
            this.state.error = `"${email}" is not a valid email address.`;
            this.state.invalid = true;
            return false;
        }
        if (this.chips.some((c) => c.toLowerCase() === email.toLowerCase())) {
            this.state.error = `${email} is already in the list.`;
            this.state.invalid = true;
            return false;
        }
        this._commit([...this.chips, email]);
        this.state.draft = "";
        this.state.error = "";
        this.state.invalid = false;
        return true;
    }

    removeChip(index) {
        const next = this.chips.slice();
        next.splice(index, 1);
        this._commit(next);
    }

    onInput(ev) {
        this.state.draft = ev.target.value;
        // Clear the inline error as soon as the user edits the draft.
        if (this.state.error) {
            this.state.error = "";
            this.state.invalid = false;
        }
    }

    onKeydown(ev) {
        const key = ev.key;
        if (key === "Enter" || key === "," || key === "Tab") {
            // Tab with an empty draft should move focus normally.
            if (key === "Tab" && !this.state.draft.trim()) {
                return;
            }
            ev.preventDefault();
            const ok = this._addEmail(this.state.draft);
            if (!ok) {
                this._focusInput();
            }
        } else if (key === "Backspace" && !this.state.draft && this.chips.length) {
            ev.preventDefault();
            this.removeChip(this.chips.length - 1);
        }
    }

    onPaste(ev) {
        const text = (ev.clipboardData || window.clipboardData).getData("text") || "";
        if (!/[,;\s\n]/.test(text)) {
            return; // single token — let normal typing/commit handle it
        }
        ev.preventDefault();
        const parts = text.split(/[,;\s\n]+/).map((p) => p.trim()).filter(Boolean);
        for (const part of parts) {
            if (this.atMax) {
                break;
            }
            // Skip exact duplicates silently; stop on first invalid.
            if (this.chips.some((c) => c.toLowerCase() === part.toLowerCase())) {
                continue;
            }
            if (!this._addEmail(part)) {
                this.state.draft = part;
                this._focusInput();
                break;
            }
        }
    }

    onBlur() {
        if (this.state.draft.trim()) {
            this._addEmail(this.state.draft);
        }
    }
}

registry.category("fields").add("biziship_email_chips", {
    component: BizishipEmailChips,
    displayName: "BiziShip Shipment Notifications",
    supportedTypes: ["char", "text"],
});
