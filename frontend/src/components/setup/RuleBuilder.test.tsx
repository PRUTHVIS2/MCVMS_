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

    // Select Heavy Vehicle Preset from dropdown
    const presetSelect = screen.getByTestId('select-preset');
    fireEvent.change(presetSelect, { target: { value: 'heavy_vehicle' } });

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

  it('toggles Always armed option, hiding days/times and sending schedule: null', () => {
    const handleSpecChange = vi.fn();
    render(
      <RuleBuilder
        zoneName="Main Perimeter"
        zoneShape="polygon"
        onSpecChange={handleSpecChange}
      />
    );

    const alwaysArmedToggle = screen.getByTestId('toggle-always-armed');
    expect(alwaysArmedToggle).not.toBeChecked();

    // Days buttons and From/To time inputs should initially be visible
    expect(screen.getByTestId('day-mon')).toBeInTheDocument();
    expect(screen.getByTestId('input-from-time')).toBeInTheDocument();
    expect(screen.getByTestId('input-to-time')).toBeInTheDocument();

    // Check "Always armed"
    fireEvent.click(alwaysArmedToggle);
    expect(alwaysArmedToggle).toBeChecked();

    // Days and times inputs should now be hidden
    expect(screen.queryByTestId('day-mon')).not.toBeInTheDocument();
    expect(screen.queryByTestId('input-from-time')).not.toBeInTheDocument();
    expect(screen.queryByTestId('input-to-time')).not.toBeInTheDocument();

    // Last call to onSpecChange should have schedule: null
    const lastCallArg = handleSpecChange.mock.calls[handleSpecChange.mock.calls.length - 1][0];
    expect(lastCallArg.schedule).toBeNull();

    // Live sentence should display "... at all times"
    const sentenceSummary = screen.getByTestId('live-sentence-summary');
    expect(sentenceSummary.textContent).toContain('at all times');

    // Uncheck "Always armed" -> restores default schedule
    fireEvent.click(alwaysArmedToggle);
    expect(alwaysArmedToggle).not.toBeChecked();

    // Days and times inputs should be visible again
    expect(screen.getByTestId('day-mon')).toBeInTheDocument();
    expect(screen.getByTestId('input-from-time')).toBeInTheDocument();

    const restoredCallArg = handleSpecChange.mock.calls[handleSpecChange.mock.calls.length - 1][0];
    expect(restoredCallArg.schedule).not.toBeNull();
    expect(restoredCallArg.schedule.from).toBe('09:00');
    expect(restoredCallArg.schedule.to).toBe('17:00');
  });

  it('displays UI note about server wall clock and marks active dates as optional', () => {
    render(
      <RuleBuilder
        zoneName="Loading Bay"
        zoneShape="polygon"
        onSpecChange={vi.fn()}
      />
    );

    // Check UI help text mentions server's wall clock
    const clockHelp = screen.getByTestId('schedule-clock-help');
    expect(clockHelp.textContent).toMatch(/server's wall clock/i);

    // Active dates should be marked optional
    expect(screen.getByText(/Active from \(optional\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Active until \(optional\)/i)).toBeInTheDocument();
  });

  it('handles presets per docs: person without visible ID has low severity with escalation', () => {
    const handleSpecChange = vi.fn();
    render(
      <RuleBuilder
        zoneName="Main Turnstile"
        zoneShape="polygon"
        onSpecChange={handleSpecChange}
      />
    );

    const presetSelect = screen.getByTestId('select-preset') as HTMLSelectElement;

    // Verify unready presets are disabled with "Available after Step N"
    const unregOption = screen.getByRole('option', {
      name: /Unregistered vehicle in zone \(Available after Step 12-13\)/i,
    }) as HTMLOptionElement;
    expect(unregOption.disabled).toBe(true);

    const idOption = screen.getByRole('option', {
      name: /Person without visible ID card \(Available after Step 17-18\)/i,
    }) as HTMLOptionElement;
    expect(idOption.disabled).toBe(true);

    // Changing to person_no_id preset (e.g. programmatically or if enabled in future)
    fireEvent.change(presetSelect, { target: { value: 'person_no_id' } });

    const lastCallArg = handleSpecChange.mock.calls[handleSpecChange.mock.calls.length - 1][0];
    expect(lastCallArg.response.severity).toBe('low');
    expect(lastCallArg.response.escalation).toEqual([
      { if_count_in_window: { n: 5, window_min: 10 }, severity: 'medium' },
    ]);
  });
});
