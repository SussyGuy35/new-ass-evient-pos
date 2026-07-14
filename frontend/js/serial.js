/**
 * EViENT POS - Web Serial API (Cash Drawer)
 * Sends ESC/POS command to open the cash drawer via serial port.
 */

let savedPort = null;

async function _fallbackToBackend() {
    try {
        const response = await api.post('/hardware/drawer');
        if (response.success) {
            console.log('Cash drawer opened via backend fallback.');
        }
    } catch (err) {
        console.error('Backend cash drawer fallback failed:', err);
        alert('Lỗi mở két tiền (Backend): ' + err.message);
    }
}

/**
 * Trigger the cash drawer open command via Web Serial API.
 * Falls back to Backend API if Web Serial is unsupported or fails.
 */
async function triggerCashDrawer() {
    // Check browser support
    if (!('serial' in navigator)) {
        console.warn('Web Serial API not supported. Falling back to backend API.');
        await _fallbackToBackend();
        return;
    }

    try {
        // Request port if not already paired
        if (!savedPort) {
            savedPort = await navigator.serial.requestPort();
        }

        // Open the serial port
        await savedPort.open({ baudRate: APP_CONFIG.BAUD_RATE });

        // Get a writer and send the command
        const writer = savedPort.writable.getWriter();
        const data = new TextEncoder().encode(APP_CONFIG.CASH_DRAWER_COMMAND);
        await writer.write(data);
        writer.releaseLock();

        // Close the port
        await savedPort.close();
    } catch (err) {
        // Reset saved port on error to allow re-pairing
        if (err.name === 'NotFoundError') {
            // User cancelled the port selection dialog
            return;
        }

        console.warn('Web Serial API failed, attempting backend fallback...', err);

        // Try to close the port if it's stuck open
        try {
            if (savedPort && savedPort.readable) {
                await savedPort.close();
            }
        } catch {
            // Ignore close errors
        }

        savedPort = null;
        await _fallbackToBackend();
    }
}
