/**
 * EViENT POS - Web Serial API (Cash Drawer)
 * Sends ESC/POS command to open the cash drawer via serial port.
 */

let savedPort = null;

async function _fallbackToWebSerial() {
    if (!('serial' in navigator)) {
        console.error('Web Serial API not supported.');
        alert('Lỗi mở két tiền: Cả server và trình duyệt đều không hỗ trợ.');
        return;
    }

    try {
        if (!savedPort) {
            savedPort = await navigator.serial.requestPort();
        }
        await savedPort.open({ baudRate: APP_CONFIG.BAUD_RATE });
        const writer = savedPort.writable.getWriter();
        const data = new TextEncoder().encode(APP_CONFIG.CASH_DRAWER_COMMAND);
        await writer.write(data);
        writer.releaseLock();
        await savedPort.close();
        console.log('Cash drawer opened via Web Serial fallback.');
    } catch (err) {
        if (err.name === 'NotFoundError') {
            return;
        }
        console.error('Web Serial API fallback failed:', err);
        try {
            if (savedPort && savedPort.readable) {
                await savedPort.close();
            }
        } catch {}
        savedPort = null;
        alert('Lỗi mở két tiền (Web Serial): ' + err.message);
    }
}

/**
 * Trigger the cash drawer open command via Backend API.
 * Falls back to Web Serial API if Backend fails.
 */
async function triggerCashDrawer() {
    try {
        const response = await api.post('/hardware/drawer');
        if (response.success) {
            console.log('Cash drawer opened via backend API.');
        } else {
            throw new Error('Backend returned failure status.');
        }
    } catch (err) {
        console.warn('Backend cash drawer failed, attempting Web Serial fallback...', err);
        await _fallbackToWebSerial();
    }
}
