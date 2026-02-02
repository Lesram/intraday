/**
 * Risk Management API Service
 * API calls for risk metrics, violations, limits, and emergency stops
 */

import { apiClient } from './api';
import type {
  RiskDashboardData,
  RiskMetric,
  RiskViolation,
  RiskLimit,
  EmergencyStop,
  UpdateRiskLimitRequest,
  TriggerEmergencyStopRequest,
} from '../types/risk';

export const riskApi = {
  // Dashboard data
  getDashboard: async (): Promise<RiskDashboardData> => {
    const response = await apiClient.get('/risk/dashboard');
    return response.data;
  },

  // Risk metrics
  getMetrics: async (): Promise<RiskMetric[]> => {
    const response = await apiClient.get('/risk/metrics');
    return response.data;
  },

  // Risk violations
  getViolations: async (resolved?: boolean): Promise<RiskViolation[]> => {
    const params = resolved !== undefined ? { resolved } : {};
    const response = await apiClient.get('/risk/violations', { params });
    return response.data;
  },

  resolveViolation: async (violationId: string): Promise<void> => {
    await apiClient.post(`/risk/violations/${violationId}/resolve`);
  },

  // Risk limits
  getLimits: async (): Promise<RiskLimit[]> => {
    const response = await apiClient.get('/risk/limits');
    return response.data;
  },

  updateLimit: async (request: UpdateRiskLimitRequest): Promise<RiskLimit> => {
    const { limit_name, ...data } = request;
    const response = await apiClient.put(`/risk/limits/${limit_name}`, data);
    return response.data;
  },

  deleteLimit: async (limitId: string): Promise<void> => {
    await apiClient.delete(`/risk/limits/${limitId}`);
  },

  // Emergency stop
  triggerEmergencyStop: async (request: TriggerEmergencyStopRequest): Promise<EmergencyStop> => {
    const response = await apiClient.post('/risk/emergency-stop', request);
    return response.data;
  },

  checkEmergencyStopActive: async (): Promise<boolean> => {
    const response = await apiClient.get('/risk/emergency-stop/active');
    return response.data;
  },

  resolveEmergencyStop: async (stopId: string): Promise<EmergencyStop> => {
    const response = await apiClient.post(`/risk/emergency-stop/${stopId}/resolve`);
    return response.data;
  },
};