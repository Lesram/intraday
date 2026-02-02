/**
 * Skip Links Component
 * Provides keyboard navigation shortcuts for screen readers
 */
import React from 'react';
import '../styles/accessibility.css';

export const SkipLinks: React.FC = () => {
  const handleSkipLink = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    e.preventDefault();
    const target = document.getElementById(targetId);
    if (target) {
      target.focus();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="skip-links-container" role="navigation" aria-label="Skip links">
      <a
        href="#main-content"
        className="skip-link"
        onClick={(e) => handleSkipLink(e, 'main-content')}
      >
        Skip to main content
      </a>
      <a
        href="#main-navigation"
        className="skip-link"
        onClick={(e) => handleSkipLink(e, 'main-navigation')}
      >
        Skip to navigation
      </a>
    </div>
  );
};
