/**
 * Chart Template Selector Component
 * Allows users to save, load, and apply chart templates
 */

import React, { useState } from 'react';
import {
  Button,
  Dropdown,
  Modal,
  Space,
  Typography,
  Input,
  Divider,
  message,
} from 'antd';
import {
  SaveOutlined,
  LayoutOutlined,
  StarOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import {
  useTemplates,
  usePresetTemplates,
  useCreateTemplate,
  useDeleteTemplate,
  useApplyTemplate,
} from '../../hooks/useChartTemplates';
import type { ChartTemplate, CreateTemplateRequest } from '../../services/chartTemplateApi';

const { Text } = Typography;

interface TemplateSelectorProps {
  chart: unknown; // TradingView chart instance
  activeIndicators: Array<{ type: string; params?: Record<string, unknown>; color?: string; panel?: number }>; // Current indicators
  onApplyTemplate: (template: ChartTemplate) => void;
}

const TemplateSelector: React.FC<TemplateSelectorProps> = ({
  chart,
  activeIndicators,
  onApplyTemplate,
}) => {
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [templateDescription, setTemplateDescription] = useState('');

  // React Query hooks
  const { data: userTemplates } = useTemplates();
  const { data: presetTemplates } = usePresetTemplates();
  const createTemplate = useCreateTemplate();
  const deleteTemplate = useDeleteTemplate();
  const applyTemplate = useApplyTemplate();

  /**
   * Capture current chart configuration
   */
  const captureCurrentChartState = (): CreateTemplateRequest => {
    // Get chart options
    const chartWithOptions = chart as { options?: () => { layout?: { background?: { type?: string } }; grid?: { vertLines?: { visible?: boolean } }; crosshair?: { mode?: number } } } | null;
    const chartOptions = chartWithOptions?.options?.() || {};

    return {
      name: templateName,
      description: templateDescription || undefined,
      layout: {
        type: 'single',
        height: 600,
        timeframe: '1D', // Get from current timeframe
      },
      indicators: activeIndicators.map((ind) => ({
        type: ind.type,
        params: ind.params || {},
        color: ind.color,
        panel: ind.panel || 0,
      })),
      drawings: [], // TODO: Capture chart drawings if needed
      settings: {
        theme: chartOptions.layout?.background?.type === 'solid' ? 'dark' : 'light',
        gridLines: chartOptions.grid?.vertLines?.visible ?? true,
        crosshair: chartOptions.crosshair?.mode !== 0,
      },
    };
  };

  const handleSaveTemplate = () => {
    if (!templateName.trim()) {
      message.error('Please enter a template name');
      return;
    }

    if (!chart) {
      message.error('Chart not initialized');
      return;
    }

    const templateData = captureCurrentChartState();

    createTemplate.mutate(templateData, {
      onSuccess: () => {
        setIsSaveModalOpen(false);
        setTemplateName('');
        setTemplateDescription('');
      },
    });
  };

  const handleApplyTemplate = (template: ChartTemplate) => {
    applyTemplate.mutate(template.id, {
      onSuccess: () => {
        onApplyTemplate(template);
      },
    });
  };

  const handleDeleteTemplate = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();

    Modal.confirm({
      title: 'Delete Template',
      content: 'Are you sure you want to delete this template?',
      okText: 'Delete',
      okType: 'danger',
      onOk: () => {
        deleteTemplate.mutate(id);
      },
    });
  };

  // Build menu items
  const menuItems: Array<{
    key?: string;
    type?: string;
    label?: React.ReactNode;
    icon?: React.ReactNode;
    disabled?: boolean;
    onClick?: () => void;
  }> = [];

  // Preset templates section
  if (presetTemplates && presetTemplates.length > 0) {
    menuItems.push({
      key: 'presets-header',
      type: 'group',
      label: 'Preset Templates',
    });

    presetTemplates.forEach((template) => {
      menuItems.push({
        key: `preset-${template.id}`,
        icon: <StarOutlined />,
        label: template.name,
        onClick: () => handleApplyTemplate(template),
      });
    });

    menuItems.push({ key: 'divider-1', type: 'divider' });
  }

  // User templates section
  if (userTemplates && userTemplates.length > 0) {
    menuItems.push({
      key: 'user-header',
      type: 'group',
      label: 'My Templates',
    });

    userTemplates.forEach((template) => {
      menuItems.push({
        key: `user-${template.id}`,
        icon: <LayoutOutlined />,
        label: (
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <span>{template.name}</span>
            <Button
              type="text"
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={(e) => handleDeleteTemplate(template.id, e)}
            />
          </Space>
        ),
        onClick: () => handleApplyTemplate(template),
      });
    });
  } else {
    menuItems.push({
      key: 'no-templates',
      disabled: true,
      label: <Text type="secondary">No saved templates</Text>,
    });
  }

  return (
    <>
      <Space.Compact>
        {/* Save Template Button */}
        <Button
          icon={<SaveOutlined />}
          onClick={() => setIsSaveModalOpen(true)}
          disabled={!chart || activeIndicators.length === 0}
        >
          Save
        </Button>

        {/* Load Template Dropdown */}
        <Dropdown
          menu={{ items: menuItems as unknown as { key: string }[] }}
          placement="bottomRight"
          trigger={['click']}
        >
          <Button icon={<LayoutOutlined />}>Templates</Button>
        </Dropdown>
      </Space.Compact>

      {/* Save Template Modal */}
      <Modal
        title="Save Chart Template"
        open={isSaveModalOpen}
        onOk={handleSaveTemplate}
        onCancel={() => {
          setIsSaveModalOpen(false);
          setTemplateName('');
          setTemplateDescription('');
        }}
        confirmLoading={createTemplate.isPending}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text>Template Name *</Text>
            <Input
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="e.g., My Day Trading Setup"
              maxLength={50}
            />
          </div>
          <div>
            <Text>Description</Text>
            <Input.TextArea
              value={templateDescription}
              onChange={(e) => setTemplateDescription(e.target.value)}
              placeholder="Optional description of this template"
              rows={3}
              maxLength={200}
            />
          </div>
          <Divider style={{ margin: '8px 0' }} />
          <div>
            <Text type="secondary">
              This template will save your current:
            </Text>
            <ul style={{ marginTop: 8, marginBottom: 0 }}>
              <li>
                <Text type="secondary">
                  Indicators ({activeIndicators.length})
                </Text>
              </li>
              <li>
                <Text type="secondary">Chart layout & settings</Text>
              </li>
            </ul>
          </div>
        </Space>
      </Modal>
    </>
  );
};

export default TemplateSelector;
