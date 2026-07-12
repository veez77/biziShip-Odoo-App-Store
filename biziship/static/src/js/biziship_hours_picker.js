/** @odoo-module **/

/**
 * BiziShip recurring weekly hours picker.
 *
 * A reusable Odoo field widget bound to a JSON Char field holding:
 *   {"start": "HH:MM", "end": "HH:MM", "days": ["MON","TUE",...]}
 *
 * Used twice — once on biziship_origin_pickup_hours ("Pickup Hours") and once on
 * biziship_dest_delivery_hours ("Delivery Hours"). The label/mode is derived from the
 * field name so the same component drives both surfaces identically.
 *
 * Renders: label row + live summary, 2-letter day pills (Mo Tu We Th Fr Sa Su),
 * and two custom 30-minute time dropdowns ("8:00 AM" to "5:00 PM").
 */

import { Component, useState, useRef, useEffect, useExternalListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export const BIZISHIP_DAYS = [
    { key: "MON", short: "Mo", label: "Mon", full: "Monday" },
    { key: "TUE", short: "Tu", label: "Tue", full: "Tuesday" },
    { key: "WED", short: "We", label: "Wed", full: "Wednesday" },
    { key: "THU", short: "Th", label: "Thu", full: "Thursday" },
    { key: "FRI", short: "Fr", label: "Fri", full: "Friday" },
    { key: "SAT", short: "Sa", label: "Sat", full: "Saturday" },
    { key: "SUN", short: "Su", label: "Sun", full: "Sunday" },
];

const DAY_ORDER = BIZISHIP_DAYS.map((d) => d.key);

// 48 options, 30-minute increments from 00:00 through 23:30 (24-hour storage).
export const BIZISHIP_TIME_OPTIONS = (() => {
    const opts = [];
    for (let i = 0; i < 48; i++) {
        const h = Math.floor(i / 2);
        const m = (i % 2) * 30;
        opts.push(`${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`);
    }
    return opts;
})();

export function fmtTime12(hhmm) {
    if (!hhmm || !hhmm.includes(":")) return hhmm || "";
    const [hs, ms] = hhmm.split(":");
    let h = parseInt(hs, 10);
    const suffix = h < 12 ? "AM" : "PM";
    h = h % 12 || 12;
    return `${h}:${ms} ${suffix}`;
}

function toMinutes(hhmm) {
    const [h, m] = (hhmm || "0:0").split(":").map((x) => parseInt(x, 10));
    return h * 60 + m;
}

function fmtDaysSummary(days) {
    const sel = DAY_ORDER.filter((k) => (days || []).includes(k));
    if (!sel.length) return "No days";
    if (sel.length === 7) return "Every day";
    if (sel.join(",") === "SAT,SUN") return "Weekends";
    if (sel.join(",") === "MON,TUE,WED,THU,FRI") return "Mon–Fri";
    const labelOf = (k) => BIZISHIP_DAYS.find((d) => d.key === k).label;
    return sel.map(labelOf).join(", ");
}

export class BizishipHoursPicker extends Component {
    static template = "biziship.HoursPicker";
    static props = { ...standardFieldProps };

    setup() {
        this.allDays = BIZISHIP_DAYS;
        this.timeOptions = BIZISHIP_TIME_OPTIONS;
        this.fmtTime12 = fmtTime12;
        this.state = useState({ openPicker: null }); // 'start' | 'end' | null
        this.rootRef = useRef("root");
        this.listRef = useRef("list");

        // Close on outside click or Escape.
        useExternalListener(window, "mousedown", (ev) => {
            if (this.rootRef.el && !this.rootRef.el.contains(ev.target)) {
                this.state.openPicker = null;
            }
        });
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape" && this.state.openPicker) {
                this.state.openPicker = null;
            }
        });

        // When a dropdown opens, center the currently-selected option.
        useEffect(
            (open) => {
                if (open && this.listRef.el) {
                    const sel = this.listRef.el.querySelector(".biziship-hp-opt.selected");
                    if (sel) {
                        sel.scrollIntoView({ block: "center" });
                    }
                }
            },
            () => [this.state.openPicker]
        );
    }

    // ---- value get/set (round-trips through the bound JSON field) ----
    get value() {
        try {
            return JSON.parse(this.props.record.data[this.props.name] || "{}") || {};
        } catch (e) {
            return {};
        }
    }
    get start() {
        return this.value.start || "08:00";
    }
    get end() {
        return this.value.end || "17:00";
    }
    get days() {
        return this.value.days || ["MON", "TUE", "WED", "THU", "FRI"];
    }

    _commit(patch) {
        const next = Object.assign(
            { start: this.start, end: this.end, days: this.days },
            patch
        );
        this.props.record.update({ [this.props.name]: JSON.stringify(next) });
    }

    // ---- derived display ----
    get isPickup() {
        return (this.props.name || "").includes("origin");
    }
    get title() {
        return this.isPickup ? "Pickup Hours" : "Delivery Hours";
    }
    get summary() {
        return `${fmtDaysSummary(this.days)} · ${fmtTime12(this.start)} – ${fmtTime12(this.end)}`;
    }
    get startDisplay() {
        return fmtTime12(this.start);
    }
    get endDisplay() {
        return fmtTime12(this.end);
    }
    get endOptions() {
        const min = toMinutes(this.start) + 30;
        return this.timeOptions.filter((t) => toMinutes(t) >= min);
    }

    isDaySelected(key) {
        return this.days.includes(key);
    }

    // ---- handlers ----
    toggleDay(key) {
        const set = new Set(this.days);
        if (set.has(key)) {
            set.delete(key);
        } else {
            set.add(key);
        }
        this._commit({ days: DAY_ORDER.filter((k) => set.has(k)) });
    }

    togglePicker(which) {
        this.state.openPicker = this.state.openPicker === which ? null : which;
    }

    selectStart(t) {
        let end = this.end;
        // If the current end is no longer ≥ start + 30 min, push it to start + 60 min.
        if (toMinutes(end) < toMinutes(t) + 30) {
            const pushed = toMinutes(t) + 60;
            const last = this.timeOptions[this.timeOptions.length - 1];
            end = pushed > toMinutes(last) ? last : this.timeOptions[Math.floor(pushed / 30)];
        }
        this._commit({ start: t, end });
        this.state.openPicker = null;
    }

    selectEnd(t) {
        this._commit({ end: t });
        this.state.openPicker = null;
    }
}

registry.category("fields").add("biziship_hours_picker", {
    component: BizishipHoursPicker,
    displayName: "BiziShip Hours Picker",
    supportedTypes: ["char", "text"],
});
