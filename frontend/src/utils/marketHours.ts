/**
 * Market Hours Utility
 * Provides market status, hours, and warnings for trading
 */

export interface MarketHours {
  isOpen: boolean;
  isExtendedHours: boolean;
  nextOpen: Date | null;
  nextClose: Date | null;
  message: string;
  canTrade: boolean;
  warning?: string;
}

/**
 * Check if current time is within regular market hours
 * Regular hours: 9:30 AM - 4:00 PM ET Monday-Friday
 */
export function getMarketStatus(): MarketHours {
  const now = new Date();
  
  // Convert to ET (Eastern Time)
  const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const hours = etTime.getHours();
  const minutes = etTime.getMinutes();
  const day = etTime.getDay(); // 0 = Sunday, 6 = Saturday
  
  // Weekend check
  if (day === 0 || day === 6) {
    const nextMonday = new Date(etTime);
    nextMonday.setDate(etTime.getDate() + (day === 0 ? 1 : 2)); // Next Monday
    nextMonday.setHours(9, 30, 0, 0);
    
    return {
      isOpen: false,
      isExtendedHours: false,
      nextOpen: nextMonday,
      nextClose: null,
      message: 'Market is closed (Weekend)',
      canTrade: false,
      warning: 'Orders placed now will be queued for Monday at 9:30 AM ET'
    };
  }
  
  // Convert time to minutes for easier comparison
  const currentMinutes = hours * 60 + minutes;
  const marketOpenMinutes = 9 * 60 + 30;  // 9:30 AM
  const marketCloseMinutes = 16 * 60;      // 4:00 PM
  const preMarketStartMinutes = 4 * 60;    // 4:00 AM
  const afterHoursEndMinutes = 20 * 60;    // 8:00 PM
  
  // Regular market hours (9:30 AM - 4:00 PM ET)
  if (currentMinutes >= marketOpenMinutes && currentMinutes < marketCloseMinutes) {
    const closeTime = new Date(etTime);
    closeTime.setHours(16, 0, 0, 0);
    
    return {
      isOpen: true,
      isExtendedHours: false,
      nextOpen: null,
      nextClose: closeTime,
      message: 'Market is OPEN',
      canTrade: true
    };
  }
  
  // Pre-market hours (4:00 AM - 9:30 AM ET)
  if (currentMinutes >= preMarketStartMinutes && currentMinutes < marketOpenMinutes) {
    const openTime = new Date(etTime);
    openTime.setHours(9, 30, 0, 0);
    
    return {
      isOpen: false,
      isExtendedHours: true,
      nextOpen: openTime,
      nextClose: null,
      message: 'Pre-Market Hours',
      canTrade: true,
      warning: 'Limited liquidity. Market orders may have wide spreads.'
    };
  }
  
  // After-hours (4:00 PM - 8:00 PM ET)
  if (currentMinutes >= marketCloseMinutes && currentMinutes < afterHoursEndMinutes) {
    const nextDay = new Date(etTime);
    nextDay.setDate(etTime.getDate() + (day === 5 ? 3 : 1)); // +3 if Friday, else +1
    nextDay.setHours(9, 30, 0, 0);
    
    return {
      isOpen: false,
      isExtendedHours: true,
      nextOpen: nextDay,
      nextClose: null,
      message: 'After-Hours Trading',
      canTrade: true,
      warning: 'Limited liquidity. Orders may not fill immediately.'
    };
  }
  
  // Overnight (8:00 PM - 4:00 AM ET)
  const nextDay = new Date(etTime);
  if (currentMinutes < preMarketStartMinutes) {
    // Early morning before pre-market
    nextDay.setHours(9, 30, 0, 0);
  } else {
    // Evening after after-hours
    nextDay.setDate(etTime.getDate() + (day === 5 ? 3 : 1)); // +3 if Friday, else +1
    nextDay.setHours(9, 30, 0, 0);
  }
  
  return {
    isOpen: false,
    isExtendedHours: false,
    nextOpen: nextDay,
    nextClose: null,
    message: 'Market is CLOSED',
    canTrade: false,
    warning: `Orders will be queued until market opens ${nextDay.toLocaleString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      hour: 'numeric', 
      minute: '2-digit',
      timeZone: 'America/New_York',
      timeZoneName: 'short'
    })}`
  };
}

/**
 * Get recommended Time-In-Force based on market status
 */
export function getRecommendedTIF(): 'day' | 'gtc' {
  const status = getMarketStatus();
  
  // Use GTC (Good-Til-Canceled) for after-hours orders
  // This prevents orders from expiring before market opens
  if (!status.isOpen) {
    return 'gtc';
  }
  
  // Use DAY for regular market hours
  return 'day';
}

/**
 * Format time until market event
 */
export function formatTimeUntil(targetDate: Date): string {
  const now = new Date();
  const diff = targetDate.getTime() - now.getTime();
  
  if (diff < 0) return 'now';
  
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  
  if (hours === 0) {
    return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
  }
  
  return `${hours} hour${hours !== 1 ? 's' : ''} ${minutes} min`;
}

/**
 * Get market status color for UI
 */
export function getMarketStatusColor(status: MarketHours): string {
  if (status.isOpen) return '#52c41a'; // Green
  if (status.isExtendedHours) return '#faad14'; // Orange
  return '#8c8c8c'; // Gray
}
