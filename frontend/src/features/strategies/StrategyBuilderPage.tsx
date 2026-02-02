/**
 * Strategy Builder - Multi-Step Wizard
 * 
 * Guided interface for creating trading strategies with pre-configured templates.
 * 
 * Architecture:
 * - 5-step wizard flow (Basic Info → Parameters → Risk → Execution → Review)
 * - Template-driven parameter forms (loads from backend)
 * - Validation at each step before progression
 * - Final submission creates strategy via POST /api/v1/strategies
 * 
 * @module features/strategies/StrategyBuilderPage
 */

import React, { useState } from 'react';
import { Steps, Card, Button, Space, App } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { StrategyFormData, StepValidation } from '@/types/strategy';
import { apiClient } from '@/services/api';
import { BasicInfoStep } from './wizard/BasicInfoStep';
import { ParametersStep } from './wizard/ParametersStep';
import { RiskLimitsStep } from './wizard/RiskLimitsStep';
import { ExecutionSettingsStep } from './wizard/ExecutionSettingsStep';
import { ReviewStep } from './wizard/ReviewStep';

const { Step } = Steps;

/**
 * Initial form data with sensible defaults
 */
const getInitialFormData = (): StrategyFormData => ({
  // Step 1
  name: '',
  description: '',
  strategyType: null,
  symbols: [],
  
  // Step 2
  parameters: {},
  
  // Step 3
  riskLimits: {
    maxPositionSize: 10000,
    dailyLossLimit: 1000,
    maxDrawdown: 0.15,
    stopLoss: 0.05,
    takeProfit: 0.10,
  },
  
  // Step 4
  executionSettings: {
    tradingHoursStart: '09:30',
    tradingHoursEnd: '16:00',
    executionFrequency: '5min',
    maxTradesPerDay: 10,
  },
});

/**
 * Strategy Builder Page
 * Main wizard container with step navigation and submission logic
 */
export const StrategyBuilderPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp(); // Use App context for messages
  
  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState<StrategyFormData>(getInitialFormData());
  const [stepValidations, setStepValidations] = useState<StepValidation[]>([
    { valid: false, errors: {} },
    { valid: false, errors: {} },
    { valid: false, errors: {} },
    { valid: false, errors: {} },
    { valid: true, errors: {} }, // Review step always valid
  ]);

  /**
   * Mutation for creating strategy
   */
  const createStrategyMutation = useMutation({
    mutationFn: async (data: StrategyFormData) => {
      // Backend expects snake_case field names
      const payload = {
        name: data.name,
        description: data.description,
        strategy_type: data.strategyType, // Convert to snake_case
        symbols: data.symbols,
        parameters: {
          ...data.parameters,
          // Include risk limits and execution settings in parameters
          riskLimits: data.riskLimits,
          executionSettings: data.executionSettings,
        },
      };
      
      console.log('Submitting strategy:', payload); // Debug log
      
      const response = await apiClient.post('/strategies', payload);
      return response.data;
    },
    onSuccess: (data) => {
      message.success(`Strategy "${data.name}" created successfully!`);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      navigate('/strategies');
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } } };
      const errorMsg = err.response?.data?.detail || 'Failed to create strategy';
      message.error(errorMsg);
      console.error('Strategy creation error:', error);
    },
  });

  /**
   * Update form data for a specific step
   */
  const updateFormData = (stepData: Partial<StrategyFormData>) => {
    setFormData(prev => ({ ...prev, ...stepData }));
  };

  /**
   * Update validation for a specific step
   */
  const updateStepValidation = (stepIndex: number, validation: StepValidation) => {
    setStepValidations(prev => {
      const updated = [...prev];
      updated[stepIndex] = validation;
      return updated;
    });
  };

  /**
   * Navigate to next step (with validation check)
   */
  const handleNext = () => {
    if (!stepValidations[currentStep].valid) {
      message.warning('Please fix validation errors before continuing');
      return;
    }
    
    setCurrentStep(prev => Math.min(prev + 1, 4));
  };

  /**
   * Navigate to previous step
   */
  const handlePrev = () => {
    setCurrentStep(prev => Math.max(prev - 1, 0));
  };

  /**
   * Submit final form data
   */
  const handleSubmit = () => {
    if (!stepValidations.every(v => v.valid)) {
      message.error('Please complete all steps before submitting');
      return;
    }
    
    createStrategyMutation.mutate(formData);
  };

  /**
   * Cancel and return to strategies list
   */
  const handleCancel = () => {
    navigate('/strategies');
  };

  /**
   * Render step content based on current step
   */
  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <BasicInfoStep
            formData={formData}
            onChange={updateFormData}
            onValidationChange={(validation: StepValidation) => updateStepValidation(0, validation)}
          />
        );
      case 1:
        return (
          <ParametersStep
            formData={formData}
            onChange={updateFormData}
            onValidationChange={(validation: StepValidation) => updateStepValidation(1, validation)}
          />
        );
      case 2:
        return (
          <RiskLimitsStep
            formData={formData}
            onChange={updateFormData}
            onValidationChange={(validation: StepValidation) => updateStepValidation(2, validation)}
          />
        );
      case 3:
        return (
          <ExecutionSettingsStep
            formData={formData}
            onChange={updateFormData}
            onValidationChange={(validation: StepValidation) => updateStepValidation(3, validation)}
          />
        );
      case 4:
        return <ReviewStep formData={formData} />;
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Card>
        <h1 style={{ marginBottom: '24px' }}>Create New Strategy</h1>
        
        {/* Step Progress Indicator */}
        <Steps current={currentStep} style={{ marginBottom: '40px' }}>
          <Step title="Basic Info" description="Name and type" />
          <Step title="Parameters" description="Strategy settings" />
          <Step title="Risk Limits" description="Risk management" />
          <Step title="Execution" description="Trading hours" />
          <Step title="Review" description="Confirm details" />
        </Steps>

        {/* Step Content */}
        <div style={{ minHeight: '400px', marginBottom: '24px' }}>
          {renderStepContent()}
        </div>

        {/* Navigation Buttons */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '24px' }}>
          <Space>
            <Button onClick={handleCancel}>Cancel</Button>
            {currentStep > 0 && (
              <Button onClick={handlePrev}>Previous</Button>
            )}
          </Space>
          
          <Space>
            {currentStep < 4 && (
              <Button 
                type="primary" 
                onClick={handleNext}
                disabled={!stepValidations[currentStep].valid}
              >
                Next
              </Button>
            )}
            {currentStep === 4 && (
              <Button 
                type="primary" 
                onClick={handleSubmit}
                loading={createStrategyMutation.isPending}
              >
                Create Strategy
              </Button>
            )}
          </Space>
        </div>
      </Card>
    </div>
  );
};
