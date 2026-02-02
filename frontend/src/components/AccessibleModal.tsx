/**
 * Accessible Modal Component
 * Modal with full keyboard navigation and screen reader support
 */
import React from 'react';
import { Modal } from 'antd';
import type { ModalProps } from 'antd';
import { useFocusTrap, useKeyboardShortcut, useAriaId } from '@/hooks/useAccessibility';

interface AccessibleModalProps extends ModalProps {
  children: React.ReactNode;
  ariaLabel?: string;
  ariaDescribedBy?: string;
}

export const AccessibleModal: React.FC<AccessibleModalProps> = ({
  children,
  open,
  onCancel,
  ariaLabel,
  ariaDescribedBy,
  title,
  ...restProps
}) => {
  const modalRef = useFocusTrap(open);
  const titleId = useAriaId('modal-title');
  const descriptionId = useAriaId('modal-description');

  // ESC to close
  useKeyboardShortcut('Escape', () => {
    if (open && onCancel) {
      onCancel({} as React.MouseEvent<HTMLButtonElement>);
    }
  });

  return (
    <Modal
      open={open}
      onCancel={onCancel}
      title={title}
      destroyOnClose
      maskClosable={true}
      keyboard={true}
      aria-modal="true"
      aria-labelledby={ariaLabel ? undefined : titleId}
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy || descriptionId}
      {...restProps}
    >
      <div ref={modalRef as React.RefObject<HTMLDivElement>}>
        {children}
      </div>
    </Modal>
  );
};
