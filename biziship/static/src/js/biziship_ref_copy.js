/** @odoo-module **/

function rpc(model, method, args, kwargs) {
    return fetch('/web/dataset/call_kw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: '2.0', method: 'call', id: Date.now(),
            params: { model: model, method: method, args: args, kwargs: kwargs || {} },
        }),
    }).then(function (r) { return r.json(); });
}

document.addEventListener('click', function (e) {
    // BOL copy-to-clipboard
    var copyEl = e.target.closest('.biziship-ref-copyable');
    if (copyEl) {
        var text = copyEl.getAttribute('data-copy-text');
        if (text) {
            navigator.clipboard.writeText(text).then(function () {
                copyEl.setAttribute('title', 'Copied ✓');
                setTimeout(function () { copyEl.setAttribute('title', 'Click to copy'); }, 1500);
            });
        }
        return;
    }

    // PRO number refresh — update only the PRO cell, no page reload
    var refreshEl = e.target.closest('.biziship-pro-refresh');
    if (!refreshEl) return;

    var orderId = parseInt(refreshEl.getAttribute('data-order-id'), 10);
    if (!orderId) return;

    refreshEl.classList.add('fa-spin');

    rpc('sale.order', 'action_biziship_refresh_documents', [[orderId]])
        .then(function (res) {
            if (res.error) throw new Error((res.error.data && res.error.data.message) || 'Refresh failed.');
            return rpc('sale.order', 'read', [[orderId], ['biziship_pro_number']]);
        })
        .then(function (res) {
            if (res.error) throw new Error((res.error.data && res.error.data.message) || 'Read failed.');
            refreshEl.classList.remove('fa-spin');
            var proNumber = res.result && res.result[0] && res.result[0].biziship_pro_number;
            var proCell = refreshEl.closest('tr').querySelector('.biziship-pro-value');
            if (proCell) {
                if (proNumber) {
                    var safe = proNumber.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
                    proCell.innerHTML = '<span class="biziship-ref-copyable" title="Click to copy" data-copy-text="' + safe + '">' + safe + '</span>';
                } else {
                    proCell.innerHTML = '<span style="color:#aaa;font-style:italic;">Was not created yet</span>';
                }
            }
        })
        .catch(function (err) {
            refreshEl.classList.remove('fa-spin');
            alert(err.message || String(err));
        });
});
