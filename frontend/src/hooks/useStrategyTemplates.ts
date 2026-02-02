/**
 * React Query hooks for Strategy Templates
 * 
 * Provides data fetching hooks for strategy template endpoints:
 * - GET /api/v1/strategies/templates - Fetch all templates
 * - GET /api/v1/strategies/templates/{type} - Fetch specific template
 * 
 * @module hooks/useStrategyTemplates
 */

import { useQuery } from '@tanstack/react-query';
import type { UseQueryResult } from '@tanstack/react-query';
import type { StrategyTemplate, StrategyType } from '../types/strategy';
import { apiClient } from '../services/api';

/**
 * Query key factory for strategy templates
 * Provides consistent query keys for React Query caching
 */
export const strategyTemplateKeys = {
  all: ['strategy-templates'] as const,
  lists: () => [...strategyTemplateKeys.all, 'list'] as const,
  list: () => [...strategyTemplateKeys.lists()] as const,
  details: () => [...strategyTemplateKeys.all, 'detail'] as const,
  detail: (type: StrategyType) => [...strategyTemplateKeys.details(), type] as const,
};

/**
 * Fetch all strategy templates
 * Returns 8 pre-configured templates with parameter definitions
 * 
 * @example
 * ```tsx
 * const { data: templates, isLoading, error } = useStrategyTemplates();
 * 
 * if (isLoading) return <Spin />;
 * if (error) return <Alert message={error.message} type="error" />;
 * 
 * return (
 *   <Select>
 *     {templates?.map(t => (
 *       <Option key={t.type} value={t.type}>{t.name}</Option>
 *     ))}
 *   </Select>
 * );
 * ```
 */
export function useStrategyTemplates(): UseQueryResult<StrategyTemplate[], Error> {
  return useQuery<StrategyTemplate[], Error>({
    queryKey: strategyTemplateKeys.list(),
    queryFn: async () => {
      const response = await apiClient.get('/strategies/templates');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes - templates rarely change
    gcTime: 30 * 60 * 1000,    // 30 minutes in cache
    retry: 2,
    refetchOnWindowFocus: false, // Templates are static
  });
}

/**
 * Fetch a specific strategy template by type
 * Returns parameter definitions and risk defaults for one template
 * 
 * @param type - Strategy type to fetch (e.g., "technical_analysis")
 * @param enabled - Whether query should auto-run (default: true)
 * 
 * @example
 * ```tsx
 * const [selectedType, setSelectedType] = useState<StrategyType | null>(null);
 * const { data: template, isLoading } = useStrategyTemplate(
 *   selectedType,
 *   { enabled: !!selectedType }
 * );
 * 
 * // Render parameter form based on template
 * return template ? (
 *   <Form>
 *     {template.parameters.map(param => (
 *       <FormItem key={param.name} label={param.label || param.name}>
 *         <InputNumber 
 *           min={param.min} 
 *           max={param.max} 
 *           defaultValue={param.default} 
 *         />
 *       </FormItem>
 *     ))}
 *   </Form>
 * ) : null;
 * ```
 */
export function useStrategyTemplate(
  type: StrategyType | null,
  options?: { enabled?: boolean }
): UseQueryResult<StrategyTemplate, Error> {
  return useQuery<StrategyTemplate, Error>({
    queryKey: type ? strategyTemplateKeys.detail(type) : ['strategy-template', 'none'],
    queryFn: async () => {
      if (!type) {
        throw new Error('Strategy type is required');
      }
      const response = await apiClient.get(`/strategies/templates/${type}`);
      return response.data;
    },
    enabled: !!type && (options?.enabled !== false),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000,    // 30 minutes
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

/**
 * Get default parameters for a strategy type
 * Extracts parameter defaults from a template
 * 
 * @param template - Strategy template
 * @returns Object with parameter defaults { paramName: defaultValue }
 * 
 * @example
 * ```tsx
 * const { data: template } = useStrategyTemplate('momentum');
 * const defaults = getDefaultParameters(template);
 * // { lookback_period: 20, threshold: 0.02, ... }
 * 
 * const [formData, setFormData] = useState(defaults);
 * ```
 */
export function getDefaultParameters(
  template: StrategyTemplate | undefined
): Record<string, unknown> {
  if (!template) return {};
  
  return template.parameters.reduce((acc, param) => {
    acc[param.name] = param.default;
    return acc;
  }, {} as Record<string, unknown>);
}
