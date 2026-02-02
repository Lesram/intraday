/**
 * Chart Template API Service
 * Handles all chart template-related API calls
 */

import axios from 'axios';
import { useAuthStore } from '@/store/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface ChartTemplate {
  id: number;
  user_id: number;
  name: string;
  description?: string;
  layout: {
    type: string;
    height?: number;
    timeframe?: string;
  };
  indicators: Array<{
    type: string;
    params: Record<string, unknown>;
    color?: string;
    panel?: number;
  }>;
  drawings: Array<{
    type: string;
    points: Array<{ time: number; price: number }>;
    style?: Record<string, unknown>;
  }>;
  settings: {
    theme?: string;
    gridLines?: boolean;
    crosshair?: boolean;
    [key: string]: unknown;
  };
  is_default: boolean;
  is_preset: boolean;
  last_used_at?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateTemplateRequest {
  name: string;
  description?: string;
  layout: ChartTemplate['layout'];
  indicators: ChartTemplate['indicators'];
  drawings: ChartTemplate['drawings'];
  settings: ChartTemplate['settings'];
  is_default?: boolean;
}

export interface UpdateTemplateRequest {
  name?: string;
  description?: string;
  layout?: ChartTemplate['layout'];
  indicators?: ChartTemplate['indicators'];
  drawings?: ChartTemplate['drawings'];
  settings?: ChartTemplate['settings'];
  is_default?: boolean;
}

/**
 * Get authorization headers
 */
const getAuthHeaders = () => {
  const token = useAuthStore.getState().accessToken;
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  };
};

/**
 * Get preset templates (no auth required)
 */
export const getPresetTemplates = async (): Promise<ChartTemplate[]> => {
  const response = await axios.get(`${API_BASE_URL}/api/v1/chart-templates/presets/`);
  return response.data;
};

/**
 * List all user templates
 */
export const listTemplates = async (): Promise<ChartTemplate[]> => {
  const response = await axios.get(
    `${API_BASE_URL}/api/v1/chart-templates/`,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Create a new template
 */
export const createTemplate = async (
  data: CreateTemplateRequest
): Promise<ChartTemplate> => {
  const response = await axios.post(
    `${API_BASE_URL}/api/v1/chart-templates`,
    data,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Get a specific template by ID
 */
export const getTemplate = async (id: number): Promise<ChartTemplate> => {
  const response = await axios.get(
    `${API_BASE_URL}/api/v1/chart-templates/${id}`,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Update a template
 */
export const updateTemplate = async (
  id: number,
  data: UpdateTemplateRequest
): Promise<ChartTemplate> => {
  const response = await axios.put(
    `${API_BASE_URL}/api/v1/chart-templates/${id}`,
    data,
    getAuthHeaders()
  );
  return response.data;
};

/**
 * Delete a template
 */
export const deleteTemplate = async (id: number): Promise<void> => {
  await axios.delete(
    `${API_BASE_URL}/api/v1/chart-templates/${id}`,
    getAuthHeaders()
  );
};

/**
 * Apply a template (tracks usage)
 */
export const applyTemplate = async (id: number): Promise<ChartTemplate> => {
  const response = await axios.post(
    `${API_BASE_URL}/api/v1/chart-templates/${id}/apply`,
    {},
    getAuthHeaders()
  );
  return response.data;
};
