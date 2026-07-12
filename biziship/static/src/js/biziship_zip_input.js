/** @odoo-module **/

/**
 * Real-time ZIP code enforcement for biziship_origin_zip and biziship_dest_zip fields.
 * - Blocks non-digit characters on keypress (beforeinput)
 * - Strips non-digits and caps at 5 on paste / drop
 * - Works in combination with the server-side onchange and write() override
 */

const ZIP_FIELD_NAMES = ['biziship_origin_zip', 'biziship_dest_zip'];

function isZipInput(target) {
    if (!target || target.tagName !== 'INPUT') return false;
    return ZIP_FIELD_NAMES.some(name =>
        target.closest(`.o_field_widget[name="${name}"]`)
    );
}

function setNativeValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
}

// Block non-digit characters and enforce max 5 on each keystroke
document.addEventListener('beforeinput', (e) => {
    if (!isZipInput(e.target)) return;

    const input = e.target;
    const { inputType, data } = e;

    if (inputType === 'insertText') {
        // Block non-digit characters
        if (!data || !/^\d+$/.test(data)) {
            e.preventDefault();
            return;
        }
        // Block if typing would exceed 5 characters
        const selLen = input.selectionEnd - input.selectionStart;
        if (input.value.length - selLen + data.length > 5) {
            e.preventDefault();
        }
    }

    // Block paste/drop via beforeinput — handled by the paste listener below
    if (inputType === 'insertFromPaste' || inputType === 'insertFromDrop') {
        e.preventDefault();
    }
}, true);

// Clean paste content: strip non-digits and cap at 5
document.addEventListener('paste', (e) => {
    if (!isZipInput(e.target)) return;

    e.preventDefault();
    const input = e.target;
    const pasted = (e.clipboardData || window.clipboardData).getData('text');
    const cleaned = pasted.replace(/\D/g, '').slice(0, 5);

    const start = input.selectionStart;
    const end = input.selectionEnd;
    const newVal = (input.value.slice(0, start) + cleaned + input.value.slice(end)).slice(0, 5);
    setNativeValue(input, newVal);
}, true);

// Clean drop content: strip non-digits and cap at 5
document.addEventListener('drop', (e) => {
    if (!isZipInput(e.target)) return;

    e.preventDefault();
    const dropped = e.dataTransfer.getData('text');
    const cleaned = dropped.replace(/\D/g, '').slice(0, 5);
    setNativeValue(e.target, cleaned);
}, true);
