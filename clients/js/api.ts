/**
 * Trading Platform API Client
 * 
 * Minimal TypeScript client for the trading platform API using fetch.
 * Handles authentication, error handling, and provides strongly typed interfaces.
 * 
 * Usage:
 *   const client = new TradingApiClient('http://localhost:8000');
 *   await client.setAuthToken('your-jwt-token');
 *   const signals = await client.getSignals('AAPL');
 */

// ============================================================================
// Types and Interfaces
// ============================================================================

export interface ApiConfig {
  baseUrl: string;
  timeout?: number;
  defaultHeaders?: Record<string, string>;
}

export interface AuthTokenData {
  access_token: string;
  token_type: string;
  expires_in?: number;
}

export interface ApiError {
  message: string;
  status: number;
  code?: string;
  details?: any;
}

export interface Signal {
  id: string;
  symbol: string;
  model_name: string;
  signal_type: 'buy' | 'sell' | 'hold';
  direction: 'long' | 'short' | 'neutral';
  strength: number;
  confidence: number;
  target_price?: number;
  stop_loss?: number;
  expiry?: string;
  strategy?: string;
  attributes?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface SignalsResponse {
  signals: Signal[];
  total: number;
  symbol?: string;
  page?: number;
  limit?: number;
}

export interface ActOnSignalRequest {
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type?: 'market' | 'limit' | 'stop' | 'stop_limit';
  tif?: 'gtc' | 'ioc' | 'fok' | 'day';
  limit_price?: number;
  stop_price?: number;
  client_order_id?: string;
  signal_id?: string;
}

export interface CreateOrderRequest {
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: 'market' | 'limit' | 'stop' | 'stop_limit';
  tif: 'gtc' | 'ioc' | 'fok' | 'day';
  limit_price?: number;
  stop_price?: number;
  client_order_id?: string;
}

export interface Order {
  id: string;
  client_idempotency_key: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: string;
  tif: string;
  status: 'accepted' | 'submitted' | 'filled' | 'partially_filled' | 'rejected' | 'cancelled';
  submitted_at: string;
  created_at: string;
  updated_at: string;
  broker_order_id?: string;
  filled_qty?: number;
  filled_avg_price?: number;
  attributes?: Record<string, any>;
}

export interface OrderResponse {
  order: Order;
  message?: string;
}

export interface Position {
  symbol: string;
  qty: number;
  avg_price: number;
  realized_pnl: number;
  unrealized_pnl?: number;
  market_value?: number;
  updated_at: string;
  created_at: string;
}

export interface PositionsResponse {
  positions: Position[];
  total: number;
}

// ============================================================================
// API Client Implementation
// ============================================================================

export class TradingApiClient {
  private config: Required<ApiConfig>;
  private authToken: string | null = null;

  constructor(baseUrl: string, options: Partial<ApiConfig> = {}) {
    this.config = {
      baseUrl: baseUrl.replace(/\/$/, ''), // Remove trailing slash
      timeout: options.timeout || 30000,
      defaultHeaders: {
        'Content-Type': 'application/json',
        ...options.defaultHeaders,
      },
    };
  }

  // ============================================================================
  // Authentication Methods
  // ============================================================================

  /**
   * Set the authentication token for API requests
   */
  setAuthToken(token: string): void {
    this.authToken = token;
  }

  /**
   * Clear the authentication token
   */
  clearAuthToken(): void {
    this.authToken = null;
  }

  /**
   * Get current authentication token
   */
  getAuthToken(): string | null {
    return this.authToken;
  }

  /**
   * Generate authorization header with JWT token
   */
  private authHeader(): Record<string, string> {
    if (!this.authToken) {
      return {};
    }
    return {
      Authorization: `Bearer ${this.authToken}`,
    };
  }

  // ============================================================================
  // HTTP Request Methods
  // ============================================================================

  /**
   * Make a GET request to the API
   */
  private async get<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    const url = this.buildUrl(endpoint, params);
    return this.request<T>(url, { method: 'GET' });
  }

  /**
   * Make a POST request to the API
   */
  private async post<T>(endpoint: string, data?: any): Promise<T> {
    const url = this.buildUrl(endpoint);
    return this.request<T>(url, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Make a PUT request to the API
   */
  private async put<T>(endpoint: string, data?: any): Promise<T> {
    const url = this.buildUrl(endpoint);
    return this.request<T>(url, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Make a DELETE request to the API
   */
  private async delete<T>(endpoint: string): Promise<T> {
    const url = this.buildUrl(endpoint);
    return this.request<T>(url, { method: 'DELETE' });
  }

  /**
   * Core request method with error handling and timeout
   */
  private async request<T>(url: string, options: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...this.config.defaultHeaders,
          ...this.authHeader(),
          ...options.headers,
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        await this.handleErrorResponse(response);
      }

      // Handle empty responses (204 No Content)
      if (response.status === 204) {
        return {} as T;
      }

      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await response.json();
      }

      // Fallback for non-JSON responses
      const text = await response.text();
      return (text as any) as T;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`Request timeout after ${this.config.timeout}ms`);
      }

      throw error;
    }
  }

  /**
   * Handle error responses and throw appropriate errors
   */
  private async handleErrorResponse(response: Response): Promise<never> {
    let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
    let errorDetails: any = null;

    try {
      const errorBody = await response.json();
      errorMessage = errorBody.message || errorBody.detail || errorMessage;
      errorDetails = errorBody;
    } catch {
      // Ignore JSON parsing errors for error responses
    }

    const apiError: ApiError = {
      message: errorMessage,
      status: response.status,
      details: errorDetails,
    };

    throw apiError;
  }

  /**
   * Build URL with query parameters
   */
  private buildUrl(endpoint: string, params?: Record<string, any>): string {
    const url = new URL(endpoint, `${this.config.baseUrl}/`);

    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    return url.toString();
  }

  // ============================================================================
  // API Endpoint Methods
  // ============================================================================

  /**
   * Get trading signals for a symbol
   */
  async getSignals(symbol: string, options: {
    page?: number;
    limit?: number;
    strategy?: string;
    signal_type?: 'buy' | 'sell' | 'hold';
  } = {}): Promise<SignalsResponse> {
    return this.get<SignalsResponse>('/api/v1/signals', {
      symbol,
      ...options,
    });
  }

  /**
   * Get a single signal by ID
   */
  async getSignal(signalId: string): Promise<Signal> {
    return this.get<Signal>(`/api/v1/signals/${signalId}`);
  }

  /**
   * Act on a trading signal (place order based on signal)
   */
  async actOnSignal(request: ActOnSignalRequest): Promise<OrderResponse> {
    return this.post<OrderResponse>('/api/v1/signals/act', request);
  }

  /**
   * Create a new order directly
   */
  async createOrder(request: CreateOrderRequest): Promise<OrderResponse> {
    return this.post<OrderResponse>('/api/v1/orders', request);
  }

  /**
   * Get an order by ID
   */
  async getOrder(orderId: string): Promise<Order> {
    return this.get<Order>(`/api/v1/orders/${orderId}`);
  }

  /**
   * Get all orders with optional filtering
   */
  async getOrders(options: {
    symbol?: string;
    status?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<{ orders: Order[]; total: number }> {
    return this.get('/api/v1/orders', options);
  }

  /**
   * Cancel an order
   */
  async cancelOrder(orderId: string): Promise<Order> {
    return this.delete<Order>(`/api/v1/orders/${orderId}`);
  }

  /**
   * Get all positions
   */
  async getPositions(): Promise<PositionsResponse> {
    return this.get<PositionsResponse>('/api/v1/positions');
  }

  /**
   * Get a specific position by symbol
   */
  async getPosition(symbol: string): Promise<Position> {
    return this.get<Position>(`/api/v1/positions/${symbol}`);
  }

  /**
   * Health check endpoint
   */
  async healthCheck(): Promise<{ status: string; timestamp: string }> {
    return this.get<{ status: string; timestamp: string }>('/health');
  }

  /**
   * Get API documentation (OpenAPI spec)
   */
  async getOpenApiSpec(): Promise<any> {
    return this.get<any>('/openapi.json');
  }
}

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * Create a configured API client instance
 */
export function createTradingApiClient(
  baseUrl: string,
  authToken?: string,
  options?: Partial<ApiConfig>
): TradingApiClient {
  const client = new TradingApiClient(baseUrl, options);
  
  if (authToken) {
    client.setAuthToken(authToken);
  }
  
  return client;
}

/**
 * Error type guard for API errors
 */
export function isApiError(error: any): error is ApiError {
  return error && typeof error.status === 'number' && typeof error.message === 'string';
}

// ============================================================================
// Default Export
// ============================================================================

export default TradingApiClient;