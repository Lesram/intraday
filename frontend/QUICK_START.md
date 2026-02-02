# Quick Start Guide - Phase 2 Frontend

## Prerequisites
- Node.js 18+ installed
- Backend server running on `http://localhost:8000`
- Backend WebSocket server on `ws://localhost:8000`

## Installation

```bash
cd frontend
npm install
```

## Development Server

```bash
npm run dev
```

The app will open at `http://localhost:5173`

## First Time Setup

1. **Start the app** → You'll be redirected to `/login`
2. **Register an account** → Click "Register" link
3. **Fill the form**:
   - Name: Your name
   - Email: valid email
   - Password: min 8 chars, uppercase+lowercase+number
4. **Submit** → Auto-login and redirect to dashboard

## What to Expect

### Login Page (`/login`)
- Email and password inputs
- Form validation
- "Register" and "Forgot Password" links
- Dark theme with green accents

### Dashboard (`/`)
- **Protected Route**: Requires authentication
- **Portfolio Stats**:
  - Portfolio Equity
  - Daily P&L (with %)
  - Buying Power
  - Positions Value
- **Additional Stats**:
  - Active Strategies
  - Pending Orders
  - Open Positions
  - Total P&L
- **Connection Status**: Top-right badge (Live/Offline)
- **Auto-refresh**: Data updates every 5-10 seconds
- **Real-time**: WebSocket pushes updates immediately

### If Backend is Not Running
- Loading spinner appears
- After timeout → error message
- Check console for API errors

## Environment Configuration

If your backend is on a different URL, create `.env`:

```env
VITE_API_URL=http://your-backend-url:port
VITE_WS_URL=ws://your-backend-url:port
```

Then update `src/services/api.ts` and `src/services/websocketManager.ts`.

## Testing Features

### Authentication
1. Login with credentials
2. Check that dashboard loads
3. Logout → redirected to login
4. Try accessing `/` → redirected to login
5. Login again → dashboard shows

### WebSocket
1. Open browser console
2. Look for: "WebSocket connected"
3. Dashboard badge should show "Live"
4. If backend sends updates → data refreshes instantly

### API Calls
1. Open React Query DevTools (bottom-left icon)
2. See active queries: `portfolio`, `orders`, `strategies`
3. Check query status: success/loading/error
4. Refetch interval: 5-15 seconds depending on query

### Error Handling
1. Stop backend server
2. Dashboard shows loading → then error alert
3. Restart backend → click "Try Again" or refresh page

## Troubleshooting

### "Network Error" on login
- Backend not running on `http://localhost:8000`
- CORS not configured on backend
- Check backend logs

### "WebSocket disconnected"
- WebSocket server not running
- Backend doesn't support Socket.IO
- Check backend WebSocket implementation

### "401 Unauthorized" after login
- JWT token format mismatch
- Backend not returning `access_token` and `refresh_token`
- Check API response format

### Dashboard shows loading forever
- API endpoint `/api/v1/portfolio` doesn't exist
- Backend not returning data in expected format
- Check console for errors

### Token refresh fails
- Endpoint `/api/v1/auth/refresh` not implemented
- `refresh_token` not accepted by backend
- User is logged out automatically

## Backend API Requirements

Your backend must implement these endpoints:

```
POST   /api/v1/auth/login
POST   /api/v1/auth/register
POST   /api/v1/auth/logout
GET    /api/v1/auth/me
POST   /api/v1/auth/refresh
GET    /api/v1/portfolio
GET    /api/v1/portfolio/positions
GET    /api/v1/orders
POST   /api/v1/orders/submit
DELETE /api/v1/orders/:id/cancel
GET    /api/v1/strategies
POST   /api/v1/strategies/:id/start
POST   /api/v1/strategies/:id/stop
```

WebSocket events to emit:
```
portfolio_update
order_update
position_update
strategy_update
market_data
signal
alert
risk_update
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript checks

## Browser DevTools

### React Query DevTools
- Click floating icon (bottom-left)
- View all active queries
- See cache data
- Manual refetch
- Clear cache

### Redux DevTools (for Zustand)
- Install Redux DevTools extension
- Open DevTools → Redux tab
- See store state changes
- Time-travel debugging (if enabled)

### Network Tab
- See all API requests
- Check JWT token in headers
- Verify response data
- Debug 401/403 errors

### Console Tab
- WebSocket connection logs
- API errors
- React warnings
- Custom logs

## Tips & Tricks

### Faster Development
1. Keep React Query DevTools open
2. Watch network tab for API errors
3. Use Redux DevTools to debug state
4. Check console for WebSocket messages

### Mock Data for Development
If backend is not ready, you can temporarily:
1. Comment out API calls in hooks
2. Return mock data from services
3. Test UI without backend

### Debugging WebSocket
Add this to `websocketManager.ts`:
```typescript
this.socket.onAny((event, ...args) => {
  console.log(`WebSocket event: ${event}`, args);
});
```

### Clear Stored Data
If auth state is corrupted:
```javascript
localStorage.removeItem('auth-storage');
location.reload();
```

## Next Steps

After Phase 2 is working:
1. **Phase 3**: Add trading features (order form, order book)
2. **Phase 4**: Strategy management (create, edit, backtest)
3. **Phase 5**: Data visualization (charts, graphs)
4. **Phase 6**: Advanced features (alerts, risk dashboard)

---

**Need Help?**
- Check `PHASE2_COMPLETE.md` for detailed documentation
- Review code examples in that file
- Check TypeScript types for API contracts
- Look at existing components for patterns

**Happy Coding! 🚀**
