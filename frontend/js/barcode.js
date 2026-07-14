/**
 * EViENT POS - Barcode Scanner (HID Mode)
 * Listens for rapid keystrokes from HID barcode scanners.
 * Distinguishes scanner input from manual typing via timeout.
 */

let barcodeBuffer = '';
let barcodeTimeout = null;

/**
 * Initialize the barcode scanner listener.
 * @param {Function} onScan - Callback invoked with the scanned barcode string.
 */
function initBarcodeScanner(onScan) {
    document.addEventListener('keydown', function (e) {
        // Skip if focus is on an input or textarea (allow normal typing)
        const tag = document.activeElement ? document.activeElement.tagName : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
            return;
        }

        if (e.key === 'Enter') {
            e.preventDefault();
            if (barcodeBuffer.length > 0) {
                onScan(barcodeBuffer);
                barcodeBuffer = '';
            }
            if (barcodeTimeout) {
                clearTimeout(barcodeTimeout);
                barcodeTimeout = null;
            }
            return;
        }

        // Only accept alphanumeric characters and common barcode chars
        if (e.key.length === 1 && /[a-zA-Z0-9\-_.]/.test(e.key)) {
            barcodeBuffer += e.key;

            // Reset timeout on each keystroke
            if (barcodeTimeout) {
                clearTimeout(barcodeTimeout);
            }
            barcodeTimeout = setTimeout(function () {
                // Timeout expired — this was likely manual typing, discard
                barcodeBuffer = '';
                barcodeTimeout = null;
            }, APP_CONFIG.BARCODE_TIMEOUT);
        }
    });
}
