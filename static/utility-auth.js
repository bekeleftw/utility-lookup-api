/**
 * Utility Lookup Authentication & Usage Tracking Module
 * Include this before the main widget script
 */

(function(window) {
  'use strict';
  
  var AUTH_URL = 'https://web-production-9acc6.up.railway.app/api/utility-auth';
  var USAGE_URL = 'https://web-production-9acc6.up.railway.app/api/utility-usage';
  
  var UtilityAuth = {
    currentUser: null,
    authToken: null,
    lastLogId: null,
    
    // Check if user is authenticated
    async checkAuth() {
      var token = localStorage.getItem('utility_auth_token');
      if (!token) return null;
      
      try {
        var res = await fetch(AUTH_URL + '/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: token })
        });
        var data = await res.json();
        
        if (data.valid) {
          this.authToken = token;
          this.currentUser = data.user;
          return data.user;
        } else {
          localStorage.removeItem('utility_auth_token');
          return null;
        }
      } catch (err) {
        console.error('Auth check failed:', err);
        return null;
      }
    },
    
    // Login user
    async login(email, password) {
      try {
        var res = await fetch(AUTH_URL + '/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email, password: password })
        });
        var data = await res.json();
        
        if (data.success) {
          localStorage.setItem('utility_auth_token', data.token);
          this.authToken = data.token;
          this.currentUser = data.user;
          return { success: true, user: data.user };
        } else {
          return { success: false, error: data.error || 'Login failed' };
        }
      } catch (err) {
        return { success: false, error: 'Connection error. Please try again.' };
      }
    },
    
    // Logout user
    logout() {
      localStorage.removeItem('utility_auth_token');
      this.authToken = null;
      this.currentUser = null;
    },
    
    // Log a search
    async logSearch(address, utilitiesRequested, results) {
      if (!this.authToken) return null;
      
      try {
        var res = await fetch(USAGE_URL + '/log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: this.authToken,
            address: address,
            utilities_requested: utilitiesRequested,
            results: results
          })
        });
        var data = await res.json();
        if (data.success) {
          this.lastLogId = data.log_id;
          return data.log_id;
        }
      } catch (err) {
        console.error('Failed to log search:', err);
      }
      return null;
    },
    
    // Submit feedback for a search
    async submitFeedback(feedback, details) {
      if (!this.authToken || !this.lastLogId) return false;
      
      try {
        await fetch(USAGE_URL + '/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: this.authToken,
            log_id: this.lastLogId,
            feedback: feedback,
            details: details || null
          })
        });
        return true;
      } catch (err) {
        console.error('Failed to submit feedback:', err);
        return false;
      }
    },
    
    // Get admin stats (admin only)
    async getStats() {
      if (!this.authToken || !this.currentUser || !this.currentUser.is_admin) {
        return null;
      }
      
      try {
        var res = await fetch(USAGE_URL + '/stats', {
          headers: { 'Authorization': 'Bearer ' + this.authToken }
        });
        var data = await res.json();
        return data.success ? data : null;
      } catch (err) {
        console.error('Failed to load stats:', err);
        return null;
      }
    },
    
    // Check if current user is admin
    isAdmin() {
      return this.currentUser && this.currentUser.is_admin;
    },
    
    // Get current user
    getUser() {
      return this.currentUser;
    }
  };
  
  // Expose to window
  window.UtilityAuth = UtilityAuth;
  
})(window);
