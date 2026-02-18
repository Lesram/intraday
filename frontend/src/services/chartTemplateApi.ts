/**
 * Chart Template API Service
 * Handles all chart template-related API calls using the centralized apiClient
 */

import { apiClient } from './api';

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
 * Get preset templates (no auth required)
 */
export const getPresetTemplates = async (): Promise<ChartTemplate[]> => {
  const response = await apiClient.get<ChartTemplate[]>('/chart-templates/presets/');
  return response.data;
};

/**
 * List all user templates
 */
export const listTemplates = async (): Promise<ChartTemplate[]> => {
  const response = await apiClient.get<ChartTemplate[]>('/chart-templates/');
  return response.data;
};

/**
 * Create a new template
 */
export const createTemplate = async (
  data: CreateTemplateRequest
): Promise<ChartTemplate> => {
  const response = await apiClient.post<ChartTemplate>('/chart-templates', data);
  return response.data;
};

/**
 * Get a specific template by ID
 */
export const getTemplate = async (id: number): Promise<ChartTemplate> => {
  const response = await apiClient.get<ChartTemplate>(`/chart-templates/${id}`);
  return response.data;
};

/**
 * Update a template
 */
export const updateTemplate = async (
  id: number,
  data: UpdateTemplateRequest
): Promise<ChartTemplate> => {
  const response = await apiClient.put<ChartTemplate>(`/chart-templates/${id}`, data);
  return response.data;
};

/**
 * Delete a template
 */
export const deleteTemplate = async (id: number): Promise<void> => {
  await apiClient.delete(`/chart-templates/${id}`);
};

/**
 * Apply a template (tracks usage)
 */
export const applyTemplate = async (id: number): Promise<ChartTemplate> => {
  const response = await apiClient.post<ChartTemplate>(`/chart-templates/${id}/apply`, {});
  return response.data;
};
