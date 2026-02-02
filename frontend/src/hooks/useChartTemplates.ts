/**
 * React Query hooks for Chart Template management
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import {
  applyTemplate,
  createTemplate,
  deleteTemplate,
  getPresetTemplates,
  getTemplate,
  listTemplates,
  updateTemplate,
  type CreateTemplateRequest,
  type UpdateTemplateRequest,
} from '../services/chartTemplateApi';

// Query keys
export const templateKeys = {
  all: ['chartTemplates'] as const,
  lists: () => [...templateKeys.all, 'list'] as const,
  presets: () => [...templateKeys.all, 'presets'] as const,
  detail: (id: number) => [...templateKeys.all, 'detail', id] as const,
};

/**
 * Hook to fetch preset templates
 */
export const usePresetTemplates = () => {
  return useQuery({
    queryKey: templateKeys.presets(),
    queryFn: getPresetTemplates,
    staleTime: Infinity, // Presets never change
  });
};

/**
 * Hook to fetch all user templates
 */
export const useTemplates = () => {
  return useQuery({
    queryKey: templateKeys.lists(),
    queryFn: listTemplates,
    staleTime: 60000, // Consider data fresh for 1 minute
  });
};

/**
 * Hook to fetch a specific template
 */
export const useTemplate = (id: number) => {
  return useQuery({
    queryKey: templateKeys.detail(id),
    queryFn: () => getTemplate(id),
    enabled: !!id,
  });
};

/**
 * Hook to create a new template
 */
export const useCreateTemplate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateTemplateRequest) => createTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
      message.success('Template saved successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to save template');
    },
  });
};

/**
 * Hook to update a template
 */
export const useUpdateTemplate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateTemplateRequest }) =>
      updateTemplate(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
      queryClient.invalidateQueries({ queryKey: templateKeys.detail(variables.id) });
      message.success('Template updated successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to update template');
    },
  });
};

/**
 * Hook to delete a template
 */
export const useDeleteTemplate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => deleteTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
      message.success('Template deleted successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to delete template');
    },
  });
};

/**
 * Hook to apply a template
 */
export const useApplyTemplate = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => applyTemplate(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: templateKeys.detail(data.id) });
      message.success('Template applied successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || 'Failed to apply template');
    },
  });
};
