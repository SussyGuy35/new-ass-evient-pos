/**
 * EViENT POS - API Client
 * HTTP client with automatic JWT authentication and error handling.
 */
class ApiClient {
    constructor() {
        this.baseUrl = APP_CONFIG.API_BASE_URL;
    }

    /**
     * Build headers with JWT token if available.
     */
    _getHeaders(hasBody = false) {
        const headers = {};
        const token = localStorage.getItem('evient_token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        if (hasBody) {
            headers['Content-Type'] = 'application/json';
        }
        return headers;
    }

    /**
     * Handle response: parse JSON, handle 401 redirect, throw on errors.
     */
    async _handleResponse(response) {
        if (response.status === 401) {
            localStorage.removeItem('evient_token');
            localStorage.removeItem('evient_user');
            window.location.href = 'login.html';
            throw new Error('Phiên đăng nhập đã hết hạn');
        }

        let data;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            data = await response.text();
        }

        if (!response.ok) {
            const message = (data && typeof data === 'object' && data.detail)
                ? data.detail
                : `Lỗi ${response.status}: ${response.statusText}`;
            throw new Error(message);
        }

        return data;
    }

    /**
     * GET request.
     */
    async get(path) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'GET',
            headers: this._getHeaders()
        });
        return this._handleResponse(response);
    }

    /**
     * POST request with JSON body.
     */
    async post(path, body = {}) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'POST',
            headers: this._getHeaders(true),
            body: JSON.stringify(body)
        });
        return this._handleResponse(response);
    }

    /**
     * PUT request with JSON body.
     */
    async put(path, body = {}) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'PUT',
            headers: this._getHeaders(true),
            body: JSON.stringify(body)
        });
        return this._handleResponse(response);
    }

    /**
     * DELETE request.
     */
    async del(path) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'DELETE',
            headers: this._getHeaders()
        });
        return this._handleResponse(response);
    }
}

// Export singleton instance
const api = new ApiClient();
