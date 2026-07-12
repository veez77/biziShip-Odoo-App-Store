/** @odoo-module **/

/**
 * BiziShip reference-numbers widget.
 *
 * Bound to a JSON Char field holding an array of reference strings:
 *   index 0 = primary "Reference Number" (sent as reference_number)
 *   index 1+ = "Additional References" (sent as additional_references)
 *
 * UI: the primary row (REF1) is always shown; the user can add up to 2 more
 * (REF2, REF3) via "+ Add another reference" and remove the extras. The cap of
 * 2 additional (3 total) is enforced here in the UI only.
 *
 * Every mutation (typing, add, remove) reads the CURRENT value of all inputs
 * from the DOM and commits the whole array in one update. This avoids a race
 * where a per-input blur-commit and an add/remove commit clobber each other
 * (which previously wiped REF1 when adding a second reference).
 */

import { Component, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const MAX_ADDITIONAL = 2; // 1 primary + 2 additional = 3 total
const MAX_LEN = 64;

export class BizishipReferences extends Component {
    static template = "biziship.References";
    static props = { ...standardFieldProps };

    setup() {
        this.rootRef = useRef("root");
    }

    // Always returns an array of at least one element (the primary row).
    get references() {
        try {
            const v = JSON.parse(this.props.record.data[this.props.name] || "[]");
            const arr = Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : "")) : [];
            return arr.length ? arr : [""];
        } catch (e) {
            return [""];
        }
    }

    get readonly() {
        return this.props.readonly;
    }

    get canAdd() {
        return !this.readonly && this.references.length < MAX_ADDITIONAL + 1;
    }

    // Live values of every reference input currently in the DOM.
    _readInputs() {
        const root = this.rootRef.el;
        if (!root) {
            return this.references;
        }
        return Array.from(root.querySelectorAll(".biziship-ref-input")).map((i) =>
            (i.value || "").slice(0, MAX_LEN)
        );
    }

    _commit(arr) {
        this.props.record.update({ [this.props.name]: JSON.stringify(arr) });
    }

    badge(index) {
        return "REF" + (index + 1);
    }

    placeholder(index) {
        return index === 0 ? "e.g. REF-12345" : "Additional reference";
    }

    onChange() {
        this._commit(this._readInputs());
    }

    addRow() {
        if (this.canAdd) {
            this._commit([...this._readInputs(), ""]);
        }
    }

    removeRow(index) {
        if (index === 0) {
            return; // the primary row is never removed
        }
        const arr = this._readInputs();
        arr.splice(index, 1);
        this._commit(arr.length ? arr : [""]);
    }
}

registry.category("fields").add("biziship_references", {
    component: BizishipReferences,
    displayName: "BiziShip Reference Numbers",
    supportedTypes: ["char", "text"],
});
