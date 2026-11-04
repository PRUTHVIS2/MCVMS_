import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RuleBuilder } from './RuleBuilder';

describe('RuleBuilder Component', () => {
  it('renders presets and updates live sentence summary on preset click', () => {
    const handleSpecChange = vi.fn();
    render(
      <RuleBuilder
        zoneName="Loading Bay"
        zoneShape="polygon"
        onSpecChange={handleSpecChange}
      />
    );

    // Initial default live sentence should be displayed
    const sentenceSummary = screen.getByTestId('live-sentence-summary');
    expect(sentenceSummary).toBeInTheDocument();
    expect(sentenceSummary.textContent).toContain('Raise a CRITICAL alert');

    // Click on Heavy Vehicle Preset
    const heavyPresetBtn = screen.getByTestId('preset-heavy-vehicle');
    fireEvent.click(heavyPresetBtn);

    expect(handleSpecChange).toHaveBeenCalled();
    expect(sentenceSummary.textContent).toContain(
      "Raise a CRITICAL alert if a truck or bus stays in 'Loading Bay' for 2 s, Mon-Sat 09:00-17:00"
    );
  });

  it('allows changing severity level dynamically', () => {
    const handleSpecChange = vi.fn();
    render(
      <RuleBuilder
        zoneName="Exit Lane"
        zoneShape="line"
        onSpecChange={handleSpecChange}
      />
    );

    // Click Medium severity
    const mediumBtn = screen.getByTestId('severity-btn-medium');
    fireEvent.click(mediumBtn);

    expect(handleSpecChange).toHaveBeenCalled();
    const sentenceSummary = screen.getByTestId('live-sentence-summary');
    expect(sentenceSummary.textContent).toContain('Raise a MEDIUM alert');
  });

  it('allows toggling schedule days and changing rule name', () => {
    const handleSpecChange = vi.fn();
    render(
      <RuleBuilder
        zoneName="North Gate"
        zoneShape="polygon"
        onSpecChange={handleSpecChange}
      />
    );

    // Edit rule name
    const nameInput = screen.getByTestId('input-rule-name');
    fireEvent.change(nameInput, { target: { value: 'Custom Night Rule' } });
    expect(handleSpecChange).toHaveBeenCalled();

    // Toggle day Sunday
    const sunBtn = screen.getByTestId('day-sun');
    fireEvent.click(sunBtn);
    expect(handleSpecChange).toHaveBeenCalled();
  });
});
