/**
 * EViENT POS - Authentication Module
 * Client-side auth: login, logout, token management, role checking.
 */
const auth = {
    /**
     * Login with username and password.
     * Stores JWT token and user object in localStorage.
     */
    async login(username, password) {
        const data = await api.post('/auth/login', { username, password });
        localStorage.setItem('evient_token', data.access_token);
        localStorage.setItem('evient_user', JSON.stringify(data.user));
        return data;
    },

    /**
     * Logout: clear stored data and redirect to login page.
     */
    logout() {
        localStorage.removeItem('evient_token');
        localStorage.removeItem('evient_user');
        window.location.href = 'login.html';
    },

    /**
     * Get stored JWT token.
     */
    getToken() {
        return localStorage.getItem('evient_token');
    },

    /**
     * Get stored user object.
     */
    getUser() {
        try {
            const user = localStorage.getItem('evient_user');
            return user ? JSON.parse(user) : null;
        } catch {
            return null;
        }
    },

    /**
     * Check if user is logged in (has a token).
     */
    isLoggedIn() {
        return !!localStorage.getItem('evient_token');
    },

    /**
     * Guard: redirect to login if not authenticated.
     * Returns the current user object.
     */
    checkAuth() {
        if (!this.isLoggedIn()) {
            window.location.href = 'login.html';
            return null;
        }
        return this.getUser();
    },

    /**
     * Check if the current user's role is in the allowed roles array.
     * Returns true if authorized, false otherwise.
     */
    checkRole(roles) {
        const user = this.getUser();
        if (!user || !user.role) return false;
        return roles.includes(user.role);
    }
};
