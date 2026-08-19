/**
 * EViENT POS - Global Configuration
 */

const APP_CONFIG = {
    // Backend API URL
    API_BASE_URL: 'http://localhost:8000/api',

    // Pagination
    ITEMS_PER_PAGE: 20,

    // Tax configuration
    VAT_RATE: 0.05,

    // Hardware settings
    BARCODE_TIMEOUT: 50,
    BAUD_RATE: 9600,
    CASH_DRAWER_COMMAND: '\x1B\x70\x00\x19\xFA',

    // VietQR Settings
    VIETQR_BANK_ID: '970436', // Vietcombank
    VIETQR_ACCOUNT_NO: '1234567890',
    VIETQR_ACCOUNT_NAME: 'CUA HANG EVIENT POS'
};
