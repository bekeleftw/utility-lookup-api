# Utility Lookup Authentication & Usage Tracking Setup

## Overview

This system adds login authentication and usage tracking to the utility lookup tool. Users must log in with email/password (managed in Airtable), and admins can see usage statistics.

## Environment Variables

Add these to your Railway deployment:

```
AIRTABLE_API_KEY=pat...your_airtable_api_key
AIRTABLE_BASE_ID=app...your_base_id
JWT_SECRET=your-secure-random-string-change-this
```

## Airtable Setup

### 1. Create Base

Create a new Airtable base (or use an existing one).

### 2. Create `utility_users` Table

| Field Name | Field Type | Notes |
|------------|------------|-------|
| email | Email | Primary identifier, must be unique |
| password_hash | Single line text | bcrypt hash (see below) |
| name | Single line text | Display name |
| is_admin | Checkbox | If checked, user sees usage stats |
| is_active | Checkbox | If unchecked, login is rejected |
| created_at | Date | Auto-set on creation |
| last_login | Date | Updated on each login |

### 3. Create `utility_usage_log` Table

| Field Name | Field Type | Notes |
|------------|------------|-------|
| user_email | Email | Links to utility_users |
| timestamp | Date (include time) | When search occurred |
| address | Single line text | Full address searched |
| utilities_requested | Single line text | Comma-separated: "electric,gas,water,internet" |
| electric_provider | Single line text | Returned provider name (or empty) |
| gas_provider | Single line text | Returned provider name (or empty) |
| water_provider | Single line text | Returned provider name (or empty) |
| internet_providers | Long text | JSON array of provider names |
| avg_confidence | Number | Average confidence score (0-1) |
| feedback | Single select | Options: "correct", "incorrect" |
| feedback_details | Long text | User notes when marking incorrect |

### 4. Create First Admin User

You need to hash the password before storing it. Run this Python script locally:

```python
import bcrypt

password = "your-secure-password"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
print(f"Password hash: {hashed}")
```

Then manually create a record in `utility_users`:
- email: admin@yourcompany.com
- password_hash: (paste the hash from above)
- name: Admin User
- is_admin: ✓ (checked)
- is_active: ✓ (checked)
- created_at: (today's date)

## API Endpoints

All endpoints are automatically available once deployed:

### Authentication

- `POST /api/utility-auth/login` - Login with email/password
- `POST /api/utility-auth/verify` - Verify JWT token

### Usage Tracking

- `POST /api/utility-usage/log` - Log a search (requires auth)
- `POST /api/utility-usage/feedback` - Submit feedback (requires auth)
- `GET /api/utility-usage/stats` - Get usage stats (admin only)

## Webflow Integration

### Option 1: Auth-Enabled Embed (Recommended)

Use `webflow_embed_with_auth_min.html` - this includes login screen, admin stats panel, and the full utility lookup tool.

1. Copy the contents of `webflow_embed_with_auth_min.html`
2. Paste into a Webflow Embed element
3. Publish

### Option 2: Separate Auth (Advanced)

If you need more control, you can:
1. Include `static/utility-auth.js` via script tag
2. Use the `UtilityAuth` object in your custom code

## Testing Checklist

- [ ] Login with valid credentials shows the tool
- [ ] Login with invalid credentials shows error
- [ ] Login with inactive user (is_active = false) shows error
- [ ] Page refresh preserves login state
- [ ] Non-admin user does NOT see stats panel
- [ ] Admin user sees stats panel with data
- [ ] Search logs correctly to Airtable
- [ ] Feedback (correct/incorrect) saves to Airtable
- [ ] Stats table shows all users with correct counts
- [ ] Logout clears session and shows login

## Troubleshooting

### "Invalid email or password"
- Check email is lowercase in Airtable
- Verify password_hash was generated correctly with bcrypt
- Ensure is_active is checked

### Stats not loading
- Verify user has is_admin checked
- Check browser console for errors
- Verify AIRTABLE_API_KEY has read access to both tables

### Searches not logging
- Check browser console for errors
- Verify AIRTABLE_API_KEY has write access to utility_usage_log
- Ensure user is logged in (token exists)

## Security Notes

1. **Change JWT_SECRET** - Use a long random string in production
2. **HTTPS only** - Ensure Railway is serving over HTTPS
3. **API Key permissions** - Use scoped Airtable API keys with minimal permissions
4. **Password requirements** - Enforce strong passwords when creating users
