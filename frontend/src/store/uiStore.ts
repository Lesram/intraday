/**
 * UI Store
 * Manages global UI state (modals, notifications, loading)
 */

import { create } from 'zustand';

// Types
export type NotificationType = 'success' | 'error' | 'warning' | 'info';

export interface Notification {
  id: string;
  type: NotificationType;
  message: string;
  description?: string;
  duration?: number;
}

export interface Modal {
  id: string;
  type: 'order' | 'strategy' | 'settings' | 'confirm';
  visible: boolean;
  data?: unknown;
}

interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;
  
  // Modals
  modals: Record<string, Modal>;
  
  // Notifications
  notifications: Notification[];
  
  // Loading states
  globalLoading: boolean;
  
  // WebSocket connection
  isWebSocketConnected: boolean;
  
  // Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  
  openModal: (id: string, type: Modal['type'], data?: unknown) => void;
  closeModal: (id: string) => void;
  
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  
  setGlobalLoading: (loading: boolean) => void;
  setWebSocketConnected: (connected: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  // Initial state
  sidebarCollapsed: false,
  modals: {},
  notifications: [],
  globalLoading: false,
  isWebSocketConnected: false,

  // Sidebar
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setSidebarCollapsed: (collapsed) =>
    set({ sidebarCollapsed: collapsed }),

  // Modals
  openModal: (id, type, data) =>
    set((state) => ({
      modals: {
        ...state.modals,
        [id]: { id, type, visible: true, data },
      },
    })),

  closeModal: (id) =>
    set((state) => ({
      modals: {
        ...state.modals,
        [id]: { ...state.modals[id], visible: false },
      },
    })),

  // Notifications
  addNotification: (notification) =>
    set((state) => ({
      notifications: [
        ...state.notifications,
        {
          ...notification,
          id: `notification-${Date.now()}-${Math.random()}`,
        },
      ],
    })),

  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),

  // Loading
  setGlobalLoading: (loading) =>
    set({ globalLoading: loading }),

  // WebSocket
  setWebSocketConnected: (connected) =>
    set({ isWebSocketConnected: connected }),
}));
