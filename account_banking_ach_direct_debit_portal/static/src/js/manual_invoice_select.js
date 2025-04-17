document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    const select = document.getElementById("manual-invoice-select");

    if (select) {
        select.addEventListener("change", function () {
            const id = select.value;
            if (id) {
                window.location.href = `/manual-payment?invoice_id=${id}`;
            }
        });
    }
});
