# Frontend Troubleshooting Guide

## Issue: Blank Page (Dark Blue Background Only)

**Date**: Current Session  
**Status**: ✅ FIXED

### Problem Description
After setting up the Vite + React + TypeScript project with Ant Design, the page displayed only a dark blue background with no visible content.

### Root Cause
**Missing Ant Design CSS Import** in `src/main.tsx`

### Solution
Added the following import to `src/main.tsx`:
```typescript
import 'antd/dist/reset.css';  // This line was missing!
```

**Complete main.tsx after fix**:
```typescript
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import 'antd/dist/reset.css';  // ← CRITICAL: Import Ant Design styles
import App from './App.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

### Why This Happened
Ant Design components require their base CSS to render properly. Without it:
- Components exist in the DOM but are invisible
- No layout, spacing, or styling is applied
- Only the page background color (from `index.css`) is visible

### Verification Steps
After the fix, you should see:
1. ✅ Header with logo, notifications, and user menu
2. ✅ Collapsible sidebar with navigation menu
3. ✅ Dashboard with 4 portfolio statistic cards
4. ✅ Proper dark theme colors and styling
5. ✅ Icons rendering correctly

---

## Common Issues & Solutions

### Issue: Port Already in Use
**Error**: "Port 5173 is in use, trying another one..."

**Solution**: Vite automatically selects the next available port (5174, 5175, etc.). This is normal and doesn't require action. Update your browser URL to the new port shown in the terminal.

---

### Issue: Module Not Found Errors
**Error**: "Cannot find module '@components/layout/MainLayout'"

**Possible Causes**:
1. TypeScript path aliases not configured correctly
2. File doesn't exist at the expected location
3. Import path has typo

**Solution**:
1. Verify `tsconfig.app.json` has path aliases:
   ```json
   {
     "compilerOptions": {
       "paths": {
         "@/*": ["./src/*"],
         "@components/*": ["./src/components/*"],
         "@features/*": ["./src/features/*"]
       }
     }
   }
   ```

2. Verify `vite.config.ts` has matching aliases:
   ```typescript
   resolve: {
     alias: {
       '@': path.resolve(__dirname, './src'),
       '@components': path.resolve(__dirname, './src/components'),
       '@features': path.resolve(__dirname, './src/features')
     }
   }
   ```

3. Check the file exists at `src/components/layout/MainLayout.tsx`

---

### Issue: Ant Design Theme Not Applied
**Symptom**: Components render but look like default light theme

**Solution**: Verify `App.tsx` wraps everything with `ConfigProvider`:
```typescript
import { ConfigProvider } from 'antd';
import { darkTheme } from './styles/theme';

function App() {
  return (
    <ConfigProvider theme={darkTheme}>
      {/* Your app content */}
    </ConfigProvider>
  );
}
```

---

### Issue: Routing Not Working (404 on Refresh)
**Symptom**: Routes work initially but show 404 when refreshing page

**Solution**: This is expected in development with Vite. The dev server handles this automatically. In production, you'll need to configure your web server to redirect all routes to `index.html`.

For Vite preview:
```typescript
// vite.config.ts
export default defineConfig({
  preview: {
    historyApiFallback: true
  }
});
```

---

### Issue: Hot Module Replacement Not Working
**Symptom**: Changes to files don't reflect in browser

**Solutions**:
1. Check the terminal for errors
2. Hard refresh the browser (Ctrl+Shift+R or Cmd+Shift+R)
3. Restart the dev server: `npm run dev`
4. Clear browser cache
5. Delete `node_modules/.vite` cache folder and restart

---

### Issue: TypeScript Errors in IDE but Build Works
**Symptom**: VS Code shows red squiggles but `npm run build` succeeds

**Solutions**:
1. Restart TypeScript server in VS Code:
   - Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
   - Type "TypeScript: Restart TS Server"
   - Press Enter

2. Verify you're using the workspace TypeScript version:
   - Open any `.ts` or `.tsx` file
   - Click the TypeScript version in the bottom-right status bar
   - Select "Use Workspace Version"

3. Delete `node_modules` and reinstall:
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   ```

---

## Debugging Checklist

When you encounter an issue:

- [ ] Check the browser console (F12 → Console tab)
- [ ] Check the terminal for build errors
- [ ] Check the Network tab for failed requests
- [ ] Verify environment variables in `.env`
- [ ] Check TypeScript errors: `npm run type-check` (if script exists)
- [ ] Check linting errors: `npm run lint`
- [ ] Restart the dev server
- [ ] Clear browser cache
- [ ] Delete `node_modules/.vite` and restart

---

## Useful Commands

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Type check (manual)
npx tsc --noEmit

# Lint code
npm run lint

# Format code
npm run format

# Clear Vite cache
rm -rf node_modules/.vite

# Reinstall dependencies
rm -rf node_modules package-lock.json && npm install
```

---

## Getting Help

If you encounter an issue not covered here:

1. Check the browser console for JavaScript errors
2. Check the terminal for build/runtime errors
3. Search the error message on Stack Overflow or GitHub Issues
4. Check Vite documentation: https://vitejs.dev/
5. Check Ant Design documentation: https://ant.design/
6. Check React Router documentation: https://reactrouter.com/

---

## Next Steps After Fixing Blank Page

Once the page is rendering correctly, proceed with:

1. ✅ **Phase 2 Week 3**: Authentication system (Login/Register pages)
2. ✅ **Phase 2 Week 4**: WebSocket integration for real-time updates
3. ✅ **Phase 2 Week 5**: State management with Zustand + React Query

See `PHASE_2_DETAILED_STEPS.md` for complete implementation guide.
